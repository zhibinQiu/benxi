"""浏览器 RPA 服务 — 供 Agent 内置工具调用。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.integrations.browser_automation.browser_config import (
    BrowserRpaConfig,
    get_browser_rpa_config,
)
from app.integrations.browser_automation.playwright_session import (
    BrowserSessionState,
    get_browser_session_manager,
    run_browser_sync,
)
from app.integrations.browser_automation.workflow_replay import (
    parse_replay_params,
    replay_workflow_steps,
)
from app.models.org import User
from app.storage.object_store import get_object_store

_logger = logging.getLogger(__name__)

REPLAY_PY_STUB = '''"""RPA 回放入口 — 平台检测到 workflow.json 时会接管实际回放。"""
import skill_runtime


def main():
    skill_runtime.finish(
        "本 Skill 含 workflow.json；请使用 run_skill_script(entry=replay.py, args=[...]) "
        "或对话中说「运行该 RPA Skill」由 browser_replay_workflow 执行。"
    )


if __name__ == "__main__":
    main()
'''


def _cfg(db: Session | None = None) -> BrowserRpaConfig:
    return get_browser_rpa_config(db)


def _require_enabled(db: Session | None = None) -> BrowserRpaConfig:
    cfg = _cfg(db)
    if not cfg.enabled:
        raise bad_request("浏览器 RPA 未启用（AGENT_BROWSER_ENABLED 或管理后台配置）")
    return cfg


async def _session_for(
    user: User,
    conversation_id: str | None,
    *,
    cfg: BrowserRpaConfig,
    create: bool = True,
) -> BrowserSessionState:
    mgr = get_browser_session_manager()
    state = await run_browser_sync(
        mgr.get_session,
        user_id=str(user.id),
        conversation_id=conversation_id,
        create=create,
        headless=cfg.headless,
    )
    if not state and create:
        raise bad_request("无法创建浏览器会话")
    if state and state.step_count >= cfg.max_steps_per_session:
        raise bad_request(
            f"本会话操作步数已达上限（{cfg.max_steps_per_session}），请新建对话或关闭会话"
        )
    return state


def _store_screenshot(user_id: uuid.UUID, session_id: str, png: bytes) -> tuple[str, str]:
    key = (
        f"browser-rpa/{user_id}/{session_id}/"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.png"
    )
    store = get_object_store()
    store.put_object_bytes(key, png, "image/png")
    return key, store.presigned_get(key, expires=7200)


def build_screenshot_api_path(storage_key: str) -> str:
    """供前端/API 代理使用的相对路径（避免 MinIO 内网 presigned 地址）。"""
    from urllib.parse import quote

    return f"/api/v1/browser-rpa/screenshot?key={quote(storage_key, safe='')}"


async def browser_navigate(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    url: str,
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    return await run_browser_sync(
        mgr.navigate,
        state,
        url,
        allowed_domains=cfg.allowed_domains,
    )


async def browser_snapshot(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
) -> dict[str, Any]:
    _require_enabled(db)
    cfg = _cfg(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    return await run_browser_sync(mgr.snapshot, state)


async def browser_click(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    ref: str,
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    return await run_browser_sync(mgr.click, state, ref)


async def browser_type(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    ref: str,
    text: str,
    submit: bool = False,
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    return await run_browser_sync(mgr.type_text, state, ref, text, submit=submit)


async def browser_fill(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    return await run_browser_sync(mgr.fill_fields, state, fields)


async def browser_screenshot(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    full_page: bool = False,
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    state = await _session_for(user, conversation_id, cfg=cfg)
    mgr = get_browser_session_manager()
    png, page_url, title = await run_browser_sync(
        mgr.screenshot_png,
        state,
        full_page=full_page,
        max_kb=cfg.screenshot_max_kb,
    )
    storage_key, presigned = _store_screenshot(user.id, state.session_id, png)
    api_path = build_screenshot_api_path(storage_key)
    return {
        "screenshot_url": presigned,
        "screenshot_api_path": api_path,
        "storage_key": storage_key,
        "page_url": page_url,
        "title": title,
    }


async def _replay_workflow_core(
    db: Session,
    user: User,
    workflow: dict[str, Any],
    params: dict[str, str],
) -> dict[str, Any]:
    cfg = _require_enabled(db)
    mgr = get_browser_session_manager()
    replay_conv = f"replay-{uuid.uuid4().hex[:8]}"
    state = await run_browser_sync(
        mgr.get_session,
        user_id=str(user.id),
        conversation_id=replay_conv,
        create=True,
        headless=cfg.headless,
    )
    if not state:
        raise bad_request("无法创建浏览器会话")
    try:
        result = await run_browser_sync(
            replay_workflow_steps,
            mgr,
            state,
            list(workflow.get("steps") or []),
            params,
            allowed_domains=cfg.allowed_domains,
            screenshot_max_kb=cfg.screenshot_max_kb,
        )
    finally:
        await run_browser_sync(
            mgr.close_session,
            user_id=str(user.id),
            conversation_id=replay_conv,
        )

    screenshot_api_path = ""
    storage_key = ""
    png = result.pop("screenshot_png", None)
    if png:
        storage_key, presigned = _store_screenshot(user.id, state.session_id, png)
        screenshot_api_path = build_screenshot_api_path(storage_key)
        result["screenshot_url"] = presigned
        result["screenshot_api_path"] = screenshot_api_path
        result["storage_key"] = storage_key

    logs = result.get("logs") or []
    conclusion = (
        f"RPA 回放完成：{result.get('title') or ''}（{result.get('url') or ''}）。"
        f"共 {len(logs)} 步。"
    )
    if screenshot_api_path:
        conclusion += f" 截图：{screenshot_api_path}"
    result["conclusion"] = conclusion
    return result


def _load_skill_workflow(db: Session, skill_name: str) -> dict[str, Any]:
    from app.services.agent_skill_service import load_skill_workspace_bytes, _skill_by_name

    skill = _skill_by_name(db, skill_name)
    if not skill.enabled:
        raise bad_request(f"Skill `{skill.name}` 已禁用")
    files = load_skill_workspace_bytes(db, skill.id)
    raw = files.get("workflow.json")
    if not raw:
        raise bad_request(f"Skill `{skill_name}` 不含 workflow.json，无法回放")
    try:
        workflow = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise bad_request("workflow.json 格式无效") from exc
    if not isinstance(workflow, dict):
        raise bad_request("workflow.json 必须是 JSON 对象")
    return workflow


async def browser_replay_workflow(
    db: Session,
    user: User,
    *,
    skill_name: str,
    parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    workflow = _load_skill_workflow(db, skill_name)
    params = {str(k): str(v) for k, v in (parameters or {}).items()}
    return await _replay_workflow_core(db, user, workflow, params)


def _replay_workflow_sync(
    db: Session,
    user: User,
    *,
    skill_name: str,
    parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    import asyncio

    workflow = _load_skill_workflow(db, skill_name)
    params = {str(k): str(v) for k, v in (parameters or {}).items()}
    return asyncio.run(_replay_workflow_core(db, user, workflow, params))


async def replay_skill_workflow_script(
    db: Session,
    user: User,
    *,
    files: dict[str, bytes],
    args: list[str] | None = None,
) -> dict[str, Any]:
    raw = files.get("workflow.json")
    if not raw:
        raise bad_request("缺少 workflow.json")
    workflow = json.loads(raw.decode("utf-8"))
    params = parse_replay_params([str(a) for a in (args or [])])
    result = await _replay_workflow_core(db, user, workflow, params)
    return {
        "status": "success",
        "conclusion": str(result.get("conclusion") or "回放完成"),
        "entry": "replay.py",
        "screenshot_api_path": result.get("screenshot_api_path"),
    }


async def browser_save_workflow(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    name: str,
    description: str = "",
    parameters: list[str] | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    _require_enabled(db)
    mgr = get_browser_session_manager()
    state = await run_browser_sync(
        mgr.get_session,
        user_id=str(user.id),
        conversation_id=conversation_id,
        create=False,
    )
    if not state or not state.workflow_steps:
        raise bad_request("当前会话无可保存的操作步骤，请先执行浏览器操作")

    skill_name = (name or "").strip().lower().replace(" ", "-")
    if not skill_name:
        raise bad_request("缺少 Skill 名称")

    params = parameters or []
    workflow = {
        "version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "steps": state.workflow_steps,
        "parameters": params,
    }
    workflow_json = json.dumps(workflow, ensure_ascii=False, indent=2)

    param_docs = "\n".join(f"- `{p}`：运行时参数（`{{{{p}}}}` 占位）" for p in params) or "- 无（步骤内 URL/文本已固定）"
    skill_body = f"""# {skill_name}（录制的 RPA 流程）

本 Skill 由 **`browser_save_workflow`** 自动生成，包含 `{len(state.workflow_steps)}` 个操作步骤。

## 参数

{param_docs}

## 回放方式

1. 对话：「运行 RPA Skill `{skill_name}`，参数 url=…」→ 智能体调用 `browser_replay_workflow`
2. 脚本：`run_skill_script(skill_name="{skill_name}", entry="replay.py", args=["key=value", ...])`

## 步骤摘要

```json
{json.dumps(state.workflow_steps[:20], ensure_ascii=False, indent=2)}
```
"""

    from app.services import agent_skill_service as skill_svc

    created = skill_svc.create_generated_skill(
        db,
        user,
        name=skill_name,
        description=description or f"浏览器 RPA 录制流程（{len(state.workflow_steps)} 步）",
        skill_md_body=skill_body,
        replace_existing=replace_existing,
        extra_files={
            "workflow.json": workflow_json,
            "replay.py": REPLAY_PY_STUB,
        },
    )
    return {
        "skill_name": created.name,
        "skill_id": str(created.id),
        "step_count": len(state.workflow_steps),
        "message": f"已保存 RPA 流程为 Skill `{created.name}`（含 replay.py）",
    }


async def browser_close_session(
    user: User,
    *,
    conversation_id: str | None,
) -> dict[str, Any]:
    mgr = get_browser_session_manager()
    await run_browser_sync(
        mgr.close_session,
        user_id=str(user.id),
        conversation_id=conversation_id,
    )
    return {"message": "浏览器会话已关闭"}


async def browser_run_task(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    task: str,
    start_url: str = "",
    max_steps: int | None = None,
) -> dict[str, Any]:
    """Phase 3：LLM 驱动的多步浏览器探索（无需 browser-use 依赖）。"""
    cfg = _require_enabled(db)
    if not cfg.auto_task_enabled:
        raise bad_request("浏览器自动探索未启用（AGENT_BROWSER_AUTO_TASK_ENABLED）")
    limit = max_steps if max_steps is not None else cfg.auto_task_max_steps
    limit = max(1, min(int(limit), cfg.max_steps_per_session))

    if start_url.strip():
        await browser_navigate(db, user, conversation_id=conversation_id, url=start_url.strip())

    from app.integrations.deepseek_client import chat_completion_message_async

    system = (
        "你是浏览器 RPA 操作员。根据任务与最新 browser_snapshot，输出唯一 JSON 对象，"
        "字段含 action（snapshot|click|type|screenshot|done）、ref、text、submit、reason。"
        "页面变化后先 snapshot。完成时 action=done。"
    )
    steps_log: list[str] = []
    last_shot: dict[str, Any] | None = None

    for i in range(limit):
        snap = await browser_snapshot(db, user, conversation_id=conversation_id)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "step": i + 1,
                        "snapshot": {
                            "url": snap.get("url"),
                            "title": snap.get("title"),
                            "refs": (snap.get("refs") or [])[:40],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        choice = await chat_completion_message_async(messages=messages, temperature=0.2)
        content = ((choice or {}).get("message") or {}).get("content") or ""
        try:
            plan = json.loads(content.strip().strip("`").replace("json\n", ""))
        except json.JSONDecodeError:
            steps_log.append(f"#{i + 1} parse_fail")
            break
        if not isinstance(plan, dict):
            break
        action = str(plan.get("action") or "").strip().lower()
        if action == "done":
            steps_log.append(f"#{i + 1} done: {plan.get('reason', '')[:80]}")
            break
        if action == "snapshot":
            steps_log.append(f"#{i + 1} snapshot")
            continue
        if action == "click":
            ref = str(plan.get("ref") or "")
            await browser_click(db, user, conversation_id=conversation_id, ref=ref)
            steps_log.append(f"#{i + 1} click {ref}")
        elif action == "type":
            ref = str(plan.get("ref") or "")
            text = str(plan.get("text") or "")
            await browser_type(
                db,
                user,
                conversation_id=conversation_id,
                ref=ref,
                text=text,
                submit=bool(plan.get("submit")),
            )
            steps_log.append(f"#{i + 1} type {ref}")
        elif action == "screenshot":
            last_shot = await browser_screenshot(db, user, conversation_id=conversation_id)
            steps_log.append(f"#{i + 1} screenshot")
        else:
            steps_log.append(f"#{i + 1} unknown:{action}")
            break

    return {
        "task": task,
        "steps": steps_log,
        "screenshot_api_path": (last_shot or {}).get("screenshot_api_path"),
        "message": f"自动探索完成，共 {len(steps_log)} 步",
    }


def schedule_browser_workflow(
    db: Session,
    user: User,
    *,
    skill_name: str,
    parameters: dict[str, str] | None = None,
    delay_minutes: int | None = None,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """Phase 3：定时回放 RPA Skill，完成后发系统通知。"""
    _require_enabled(db)
    _load_skill_workflow(db, skill_name)

    now = datetime.now(timezone.utc)
    if scheduled_at:
        try:
            run_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise bad_request("scheduled_at 格式无效") from exc
    elif delay_minutes is not None:
        run_at = now + timedelta(minutes=max(1, int(delay_minutes)))
    else:
        raise bad_request("请提供 delay_minutes 或 scheduled_at")

    from app.models.scheduled_rpa_task import ScheduledRpaTask

    row = ScheduledRpaTask(
        user_id=user.id,
        skill_name=skill_name.strip(),
        parameters=parameters or {},
        scheduled_at=run_at,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    from app.services.background_job_dispatch import dispatch_scheduled_rpa_task

    countdown = max(0, int((run_at - now).total_seconds()))
    dispatch_scheduled_rpa_task(row.id, countdown=countdown)

    return {
        "task_id": str(row.id),
        "skill_name": skill_name,
        "scheduled_at": run_at.isoformat(),
        "message": f"已安排 RPA 任务 `{skill_name}` 于 {run_at.isoformat()} 执行",
    }


def deliver_scheduled_rpa_task(task_id: uuid.UUID) -> dict[str, Any]:
    from app.database import SessionLocal
    from app.models.scheduled_rpa_task import ScheduledRpaTask
    from app.models.org import User
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        row = db.get(ScheduledRpaTask, task_id)
        if not row or row.cancelled_at or row.status == "completed":
            return {"status": "skipped"}

        user = db.get(User, row.user_id)
        if not user:
            row.status = "failed"
            row.result_summary = "用户不存在"
            db.commit()
            return {"status": "failed"}

        now = datetime.now(timezone.utc)
        if row.scheduled_at > now + timedelta(seconds=5):
            from app.services.background_job_dispatch import dispatch_scheduled_rpa_task

            countdown = max(0, int((row.scheduled_at - now).total_seconds()))
            dispatch_scheduled_rpa_task(row.id, countdown=countdown)
            return {"status": "rescheduled", "countdown": countdown}

        try:
            result = _replay_workflow_sync(
                db,
                user,
                skill_name=row.skill_name,
                parameters={str(k): str(v) for k, v in (row.parameters or {}).items()},
            )
            row.status = "completed"
            row.completed_at = datetime.now(timezone.utc)
            row.result_summary = str(result.get("conclusion") or "")[:2000]
            row.screenshot_key = str(result.get("storage_key") or "") or None
            link = str(result.get("screenshot_api_path") or "") or None
            create_notification(
                db,
                user_id=user.id,
                title=f"RPA 任务完成：{row.skill_name}",
                body=row.result_summary or "回放已完成",
                link=link,
            )
            db.commit()
            return {"status": "completed", "task_id": str(task_id)}
        except Exception as exc:
            _logger.warning("scheduled RPA %s failed: %s", task_id, exc)
            row.status = "failed"
            row.completed_at = datetime.now(timezone.utc)
            row.result_summary = str(exc)[:500]
            db.commit()
            return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def fetch_screenshot_bytes(storage_key: str) -> bytes | None:
    if not storage_key or ".." in storage_key or not storage_key.startswith("browser-rpa/"):
        return None
    try:
        return get_object_store().get_object_bytes(storage_key)
    except Exception:
        return None
