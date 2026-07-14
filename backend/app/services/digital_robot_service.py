"""数字机器人 RPA 任务管理服务 — 对话规划 + CRUD + 调度执行。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.digital_robot_task import DigitalRobotTask
from app.models.org import User
from app.schemas.digital_robot import RpaPlan, RpaStep
from app.services import platform_chat_store
from app.database import SessionLocal

logger = logging.getLogger(__name__)

_PLAN_SYSTEM_PROMPT = """你是「小析」，本析平台的数字机器人助手。
你的职责是：
1. 理解用户的 RPA（浏览器自动化）任务需求
2. 将任务拆解为可执行的浏览器操作步骤
3. 在回复中附上 JSON 格式的执行计划

可用的浏览器操作：
- navigate(params={url}) — 导航到目标页面
- snapshot(params={}) — 获取页面快照与可交互元素 ref
- click(params={ref}) — 点击某个元素
- type(params={ref, text, submit?}) — 向输入框输入文字
- fill(params={fields: [{ref, value}]}) — 批量填表
- screenshot(params={full_page?}) — 截图

如果用户的问题是通用问题（非 RPA 任务），按普通客服回答即可，不生成计划。
如果用户描述的是 RPA 任务，请在回复末尾附上 JSON 计划块：

```json
{
  "plan": {
    "summary": "任务概述",
    "target_url": "https://example.com",
    "steps": [
      {"operation": "navigate", "params": {"url": "https://..."}, "description": "打开登录页面"},
      {"operation": "type", "params": {"ref": "e1", "text": "用户名"}, "description": "输入用户名"},
      {"operation": "type", "params": {"ref": "e2", "text": "密码"}, "description": "输入密码"},
      {"operation": "click", "params": {"ref": "e3"}, "description": "点击登录按钮"},
      {"operation": "screenshot", "params": {"full_page": false}, "description": "截图确认"}
    ]
  }
}
```

回答风格：先说明任务理解，给出计划概览，再附上 JSON 块。"""


# ── LLM 对话规划 ─────────────────────────────────────

def _build_messages(message: str, history: list[dict]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
    ]
    for msg in history:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": message})
    return messages


def _extract_plan_from_reply(reply: str) -> RpaPlan | None:
    match = re.search(r"```json\s*\n(.*?)```", reply, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1).strip())
        plan_data = data.get("plan") or data
        if not isinstance(plan_data, dict):
            return None
        steps_data = plan_data.get("steps", [])
        steps = [
            RpaStep(operation=s.get("operation", ""), params=s.get("params", {}), description=s.get("description", ""))
            for s in steps_data
        ]
        return RpaPlan(steps=steps, summary=plan_data.get("summary", ""), target_url=plan_data.get("target_url", ""))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("计划 JSON 解析失败: %s", exc)
        return None


async def chat_with_digital_robot(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[dict],
    conversation_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("数字机器人未配置，请联系管理员配置 DeepSeek API")
    messages = _build_messages(message, history)
    api_key, base_url, model = resolve_credentials()
    payload = {"model": model, "messages": messages, "temperature": 0.3}
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"数字机器人暂时不可用: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e
    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    reply = (choices[0].get("message", {}) or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        raise bad_request("AI 返回为空")
    plan = _extract_plan_from_reply(reply)
    conv = platform_chat_store.get_or_create_conversation(
        db, user_id=user.id, scope="digital-robot", conversation_id=conversation_id,
    )
    platform_chat_store.append_turn(db, conversation=conv, user_message=message, assistant_message=reply)
    db.commit()
    return {
        "reply": reply,
        "model": model,
        "conversation_id": str(conv.id),
        "plan": plan.model_dump() if plan else None,
    }


# ── RPA 计划执行 ─────────────────────────────────────

async def execute_rpa_plan(
    db: Session,
    user: User,
    *,
    plan: RpaPlan,
    conversation_id: str | None = None,
) -> dict:
    from app.services import browser_rpa_service as rpa
    execution_log: list[str] = []
    screenshot_urls: list[str] = []
    for step in plan.steps:
        op = step.operation
        params = step.params
        execution_log.append(f"[{op}] {step.description}")
        logger.info("数字机器人执行步骤: [%s] %s", op, step.description)
        try:
            if op == "navigate":
                url = params.get("url", "")
                result = await rpa.browser_navigate(db, user, conversation_id=conversation_id, url=url)
                execution_log.append(f"  → 导航完成: {result.get('url', url)}")
            elif op == "snapshot":
                result = await rpa.browser_snapshot(db, user, conversation_id=conversation_id)
                execution_log.append(f"  → 快照完成: {len(result.get('refs', []))} 个可交互元素")
            elif op == "click":
                ref = params.get("ref", "")
                await rpa.browser_click(db, user, conversation_id=conversation_id, ref=ref)
                execution_log.append(f"  → 点击完成: ref={ref}")
            elif op == "type":
                ref = params.get("ref", "")
                text = params.get("text", "")
                submit = params.get("submit", False)
                await rpa.browser_type(db, user, conversation_id=conversation_id, ref=ref, text=text, submit=submit)
                execution_log.append(f"  → 输入完成: ref={ref}")
            elif op == "fill":
                for field in params.get("fields", []):
                    await rpa.browser_type(
                        db, user, conversation_id=conversation_id,
                        ref=field.get("ref", ""), text=field.get("value", ""),
                    )
                execution_log.append(f"  → 批量填表完成: {len(params.get('fields', []))} 个字段")
            elif op == "screenshot":
                result = await rpa.browser_screenshot(
                    db, user, conversation_id=conversation_id, full_page=params.get("full_page", False),
                )
                if isinstance(result, dict):
                    key = result.get("storage_key", "")
                    if key:
                        screenshot_urls.append(rpa.build_screenshot_api_path(key))
                execution_log.append("  → 截图完成")
            else:
                execution_log.append(f"  ⚠ 未知操作: {op}，已跳过")
        except Exception as exc:
            err_msg = f"  ✗ 执行失败: {exc}"
            execution_log.append(err_msg)
            logger.warning("数字机器人步骤执行异常: %s", err_msg)
    return {"success": True, "message": f"RPA 计划执行完成，共 {len(plan.steps)} 步", "screenshot_urls": screenshot_urls, "execution_log": execution_log}


# ── 周期调度辅助 ─────────────────────────────────────

def _calc_next_run(task: DigitalRobotTask) -> datetime | None:
    now = datetime.now(timezone.utc)
    if task.schedule_mode == "immediate":
        return None
    if task.schedule_mode == "scheduled":
        return task.scheduled_at if task.scheduled_at and task.scheduled_at > now else None
    if task.schedule_mode == "periodic":
        if task.cron_expression:
            try:
                from croniter import croniter
                cron = croniter(task.cron_expression, now)
                return cron.get_next(datetime)
            except ImportError:
                logger.warning("croniter 未安装，无法解析 cron")
            except Exception as exc:
                logger.warning("cron 解析失败: %s", exc)
            return None
        if task.interval_seconds and task.interval_seconds > 0:
            base = task.last_run_at or task.scheduled_at or now
            return base + timedelta(seconds=task.interval_seconds)
    return None


# ── 后台线程执行 ─────────────────────────────────────

def _run_task_in_background(task_id_hex: str) -> None:
    """后台线程：执行 RPA 任务并更新状态。"""
    import uuid
    db = SessionLocal()
    try:
        task = db.get(DigitalRobotTask, uuid.UUID(hex=task_id_hex))
        if not task or task.status in ("running", "done", "cancelled"):
            return
        task.status = "running"
        db.flush()

        plan_data = task.plan_json or {}
        steps = [
            RpaStep(operation=s.get("operation", ""), params=s.get("params", {}), description=s.get("description", ""))
            for s in plan_data.get("steps", [])
        ]
        plan = RpaPlan(steps=steps, summary=plan_data.get("summary", ""), target_url=plan_data.get("target_url", ""))

        user = db.get(User, task.user_id)
        if not user:
            task.status = "failed"
            task.error_message = "用户不存在"
            db.commit()
            return

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(execute_rpa_plan(db, user, plan=plan, conversation_id=f"task-{task_id_hex[:8]}"))
        finally:
            loop.close()

        now = datetime.now(timezone.utc)
        task.last_run_at = now
        task.last_result_summary = result.get("message", "")
        task.execution_count = (task.execution_count or 0) + 1
        task.status = "done"
        task.error_message = None

        next_run = _calc_next_run(task)
        task.next_run_at = next_run
        if next_run:
            countdown = max(0, int((next_run - now).total_seconds()))
            if countdown > 0:
                task.status = "scheduled"
                threading.Timer(countdown, _run_task_in_background, args=[task_id_hex]).start()
        db.commit()
        logger.info("数字机器人任务 %s 执行完成", task_id_hex)

    except Exception as exc:
        logger.exception("数字机器人任务 %s 异常", task_id_hex)
        try:
            task = db.get(DigitalRobotTask, uuid.UUID(hex=task_id_hex))
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── CRUD ─────────────────────────────────────────────

def create_task(db: Session, user: User, data: dict) -> DigitalRobotTask:
    now = datetime.now(timezone.utc)
    task = DigitalRobotTask(
        user_id=user.id,
        title=data.get("title", "未命名任务"),
        description=data.get("description", ""),
        plan_json=data.get("plan"),
        schedule_mode=data.get("schedule_mode", "immediate"),
        scheduled_at=data.get("scheduled_at"),
        cron_expression=data.get("cron_expression"),
        interval_seconds=data.get("interval_seconds"),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    if task.schedule_mode == "scheduled" and task.scheduled_at:
        task.status = "scheduled"
        task.next_run_at = task.scheduled_at
    elif task.schedule_mode == "periodic":
        task.status = "scheduled"
        task.next_run_at = _calc_next_run(task)
    elif task.schedule_mode == "immediate":
        task.status = "pending"
        task.next_run_at = now

    db.add(task)
    db.flush()
    _do_dispatch(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, user: User, task_id: str, data: dict) -> DigitalRobotTask:
    from uuid import UUID
    tid = UUID(hex=task_id) if isinstance(task_id, str) and len(task_id) == 32 else UUID(task_id)
    task = db.get(DigitalRobotTask, tid)
    if not task or task.user_id != user.id:
        raise not_found("任务不存在")
    for key in ("title", "description", "schedule_mode", "scheduled_at", "cron_expression", "interval_seconds"):
        if key in data:
            setattr(task, key, data[key])
    if "plan" in data:
        task.plan_json = data["plan"]

    now = datetime.now(timezone.utc)
    if task.schedule_mode == "scheduled" and task.scheduled_at:
        task.status = "scheduled"
        task.next_run_at = task.scheduled_at
    elif task.schedule_mode == "periodic":
        task.status = "scheduled"
        task.next_run_at = _calc_next_run(task)
    elif task.schedule_mode == "immediate":
        task.status = "pending"
        task.next_run_at = now

    task.updated_at = now
    db.commit()
    _do_dispatch(task)
    db.refresh(task)
    return task


def _do_dispatch(task: DigitalRobotTask) -> None:
    """根据任务状态调度执行。"""
    now = datetime.now(timezone.utc)
    if task.status == "scheduled" and task.next_run_at:
        countdown = max(0, int((task.next_run_at - now).total_seconds()))
        if countdown == 0:
            _run_task_in_background(task.id.hex)
        else:
            threading.Timer(countdown, _run_task_in_background, args=[task.id.hex]).start()
    elif task.status == "pending" and task.schedule_mode == "immediate":
        _run_task_in_background(task.id.hex)


def list_tasks(
    db: Session, user: User, *, status: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[DigitalRobotTask], int]:
    base = select(DigitalRobotTask).where(DigitalRobotTask.user_id == user.id)
    count_q = select(sa_func.count()).select_from(DigitalRobotTask).where(DigitalRobotTask.user_id == user.id)
    if status and status != "all":
        base = base.where(DigitalRobotTask.status == status)
        count_q = count_q.where(DigitalRobotTask.status == status)
    total = db.scalar(count_q) or 0
    rows = list(db.scalars(base.order_by(DigitalRobotTask.updated_at.desc()).offset(offset).limit(limit)).all())
    return rows, total


def get_task(db: Session, user: User, task_id: str) -> DigitalRobotTask:
    from uuid import UUID
    tid = UUID(hex=task_id) if isinstance(task_id, str) and len(task_id) == 32 else UUID(task_id)
    task = db.get(DigitalRobotTask, tid)
    if not task or task.user_id != user.id:
        raise not_found("任务不存在")
    return task


def delete_task(db: Session, user: User, task_id: str) -> None:
    from uuid import UUID
    tid = UUID(hex=task_id) if isinstance(task_id, str) and len(task_id) == 32 else UUID(task_id)
    task = db.get(DigitalRobotTask, tid)
    if not task or task.user_id != user.id:
        raise not_found("任务不存在")
    db.delete(task)
    db.commit()


def execute_task_now(db: Session, user: User, task_id: str) -> DigitalRobotTask:
    """立即执行任务（无视原调度配置）。"""
    from uuid import UUID
    tid = UUID(hex=task_id) if isinstance(task_id, str) and len(task_id) == 32 else UUID(task_id)
    task = db.get(DigitalRobotTask, tid)
    if not task or task.user_id != user.id:
        raise not_found("任务不存在")
    if not task.plan_json:
        raise bad_request("任务没有执行计划")
    task.status = "running"
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    _run_task_in_background(task.id.hex)
    return task
