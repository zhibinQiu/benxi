"""父智能体任务编排 — 规划清单、顺序执行、验收与重试。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.agent_profiles import get_agent_profile, resolve_agent_title
from app.core.aip.messaging import reply_text_from_complete
from app.core.aip.types import AipMessage

MAX_TASK_ATTEMPTS = 2


@dataclass
class OrchestratorTask:
    id: str
    title: str
    agent_id: str
    reason: str
    status: str = "pending"
    summary: str = ""
    attempts: int = 0
    last_error: str = ""


def tasks_from_routes(routes: list[Any]) -> list[OrchestratorTask]:
    """将路由列表转为最小任务清单（一条路由一项，不臆造额外任务）。"""
    tasks: list[OrchestratorTask] = []
    for idx, route in enumerate(routes, start=1):
        profile = get_agent_profile(route.agent_id)
        title = profile.title if profile else route.agent_id
        tasks.append(
            OrchestratorTask(
                id=f"t{idx}",
                title=title,
                agent_id=route.agent_id,
                reason=route.reason,
            )
        )
    return tasks


def _task_to_json(task: OrchestratorTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "agent_id": task.agent_id,
        "status": task.status,
        "summary": task.summary[:200] if task.summary else "",
    }


def workflow_plan_tasks(
    tasks: list[OrchestratorTask],
    *,
    step_id: str,
    mode: str = "sequential",
) -> dict[str, Any]:
    chain = " → ".join(t.title for t in tasks)
    detail = chain or f"共 {len(tasks)} 项"
    return {
        "type": "workflow",
        "data": {
            "phase": "plan_tasks",
            "title": "规划方案",
            "detail": detail,
            "tool": "supervisor.plan",
            "step_id": step_id,
            "mode": mode,
            "tasks": [_task_to_json(t) for t in tasks],
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }


def workflow_task_event(
    phase: str,
    task: OrchestratorTask,
    *,
    step_id: str,
    detail: str = "",
    attempt: int | None = None,
    all_tasks: list[OrchestratorTask] | None = None,
) -> dict[str, Any]:
    snapshot = all_tasks if all_tasks is not None else [task]
    data: dict[str, Any] = {
        "phase": phase,
        "task_id": task.id,
        "title": task.title,
        "detail": detail[:240],
        "tool": "supervisor.task",
        "step_id": step_id,
        "agent_id": task.agent_id,
        "agent_title": _agent_title(task.agent_id),
        "tasks": [_task_to_json(t) for t in snapshot],
    }
    if attempt is not None:
        data["attempt"] = attempt
    if phase in ("task_done", "task_failed"):
        data["status"] = "done" if phase == "task_done" else "failed"
    return {"type": "workflow", "data": data}


def _agent_title(agent_id: str) -> str:
    return resolve_agent_title(agent_id)


def _successful_tool_summaries_in_events(events: list[dict[str, Any]]) -> list[str]:
    from app.services.agent_reply_synth import is_internal_tool_outcome_line

    summaries: list[str] = []
    for event in events:
        if event.get("type") != "workflow":
            continue
        data = event.get("data") or {}
        if data.get("phase") != "tool_result":
            continue
        if data.get("status") == "failed":
            continue
        detail = str(data.get("detail") or "").strip()
        title = str(data.get("result_title") or data.get("title") or "").strip()
        text = detail or title
        if not text or is_internal_tool_outcome_line(text):
            continue
        if title and is_internal_tool_outcome_line(f"{title}：{detail}"):
            continue
        summaries.append(text)
    return summaries


def _tool_failed_in_events(events: list[dict[str, Any]]) -> tuple[bool, str]:
    for event in events:
        if event.get("type") != "workflow":
            continue
        data = event.get("data") or {}
        if data.get("phase") != "tool_result":
            continue
        if data.get("status") == "failed":
            detail = str(data.get("detail") or data.get("title") or "工具失败").strip()
            return True, detail[:160]
    return False, ""


_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_PLAIN_SCREENSHOT_URL_RE = re.compile(
    r"(?:/ai)?/api/v1/browser-rpa/screenshot\?key=[^\s<>\"')\]]+"
)


def extract_image_attachments_from_markdown(
    reply: str | None,
) -> list[dict[str, Any]]:
    """从回复 Markdown 或裸 URL 中解析浏览器截图附件。"""
    text = str(reply or "")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _append(url: str, title: str = "浏览器截图") -> None:
        clean = url.strip()
        if not clean or "/browser-rpa/screenshot" not in clean or clean in seen:
            return
        seen.add(clean)
        out.append({"type": "image", "url": clean, "title": title or "浏览器截图"})

    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        title = (match.group(1) or "浏览器截图").strip() or "浏览器截图"
        _append(match.group(2) or "", title)
    for match in _PLAIN_SCREENSHOT_URL_RE.finditer(text):
        _append(match.group(0) or "")
    return out


def collect_screenshot_attachments_from_task_results(
    results: list[Any],
) -> list[dict[str, Any]]:
    """合并子任务 attachment 事件与 hop complete 回复中的截图。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in results:
        for att in collect_image_attachments_from_events(item.events):
            url = str(att.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(att)
        complete = item.complete or {}
        for att in extract_image_attachments_from_markdown(
            str(complete.get("reply") or "")
        ):
            url = str(att.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(att)
    return out


def collect_image_attachments_from_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从子任务事件流中提取浏览器截图等图片附件（按 url 去重）。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "attachment":
            continue
        data = event.get("data") or {}
        if data.get("type") != "image":
            continue
        url = str(data.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(dict(data))
    return out


def append_screenshot_markdown_to_reply(
    reply: str | None,
    attachments: list[dict[str, Any]],
) -> str | None:
    """在最终回复末尾追加 Markdown 图片引用，便于持久化与前端展示。"""
    if not attachments:
        return reply
    parts: list[str] = []
    base = (reply or "").strip()
    if base:
        parts.append(base)
    image_blocks: list[str] = []
    for att in attachments:
        url = str(att.get("url") or "").strip()
        if not url or url in base:
            continue
        title = str(att.get("title") or "浏览器截图").strip() or "浏览器截图"
        image_blocks.append(f"![{title}]({url})")
    if not image_blocks:
        return reply if not parts else "\n\n".join(parts).strip()
    if base and "页面截图" not in base:
        parts.append("### 页面截图")
    parts.extend(image_blocks)
    merged = "\n\n".join(parts).strip()
    return merged or None


def _reply_from_complete(complete: dict[str, Any] | None) -> str:
    return reply_text_from_complete(complete)


def verify_task_result(
    task: OrchestratorTask,
    events: list[dict[str, Any]],
    complete: dict[str, Any] | None,
) -> tuple[bool, str, str]:
    """规则验收：专精 handoff 可验收且非推脱即通过。"""
    failed, fail_detail = _tool_failed_in_events(events)
    if failed:
        return (
            False,
            "",
            f"请修正后重试：{fail_detail}" if fail_detail else "上次工具调用失败，请换用正确工具重试",
        )

    reply = _reply_from_complete(complete)
    if reply:
        from app.services.agent_reply_synth import reply_looks_like_denial

        if not reply_looks_like_denial(reply):
            summary = reply.split("\n", 1)[0].strip()[:160]
            if len(summary) < 8 and len(reply) > 8:
                summary = reply[:160]
            return True, summary, ""

    citations = list((complete or {}).get("citations") or [])
    tool_summaries = _successful_tool_summaries_in_events(events)
    if tool_summaries:
        from app.services.agent_reply_synth import reply_looks_like_denial

        if not reply or reply_looks_like_denial(reply):
            return True, tool_summaries[-1], ""

    if not reply:
        return False, "", "请调用平台工具完成该步骤，勿仅口头说明无法操作"

    if any(
        marker in reply
        for marker in (
            "无法完成",
            "无直接创建",
            "无查询接口",
            "无定时提醒",
            "建议您手动",
            "请联系系统管理员",
        )
    ) and not citations:
        return (
            False,
            "",
            "请勿推脱；请使用已分配的工具完成操作，或在确实无工具时明确说明已尝试的工具名",
        )

    summary = reply.split("\n", 1)[0].strip()[:160]
    if len(summary) < 8 and len(reply) > 8:
        summary = reply[:160]
    return True, summary, ""


def build_retry_user_message(
    original: str,
    task: OrchestratorTask,
    retry_hint: str,
) -> str:
    return (
        f"{original.strip()}\n\n"
        f"【重试 · {task.title}】{retry_hint.strip()}"
    )


def build_task_plan_workflow_update(tasks: list[OrchestratorTask]) -> list[dict[str, Any]]:
    return [_task_to_json(t) for t in tasks]


def new_plan_step_id() -> str:
    return f"agent-plan-{uuid.uuid4().hex[:8]}"


def new_task_step_id(task_id: str) -> str:
    return f"agent-task-{task_id}-{uuid.uuid4().hex[:6]}"


@dataclass
class TaskExecutionResult:
    task: OrchestratorTask
    route: Any
    events: list[dict[str, Any]] = field(default_factory=list)
    complete: dict[str, Any] | None = None
    satisfied: bool = False
    aip_handoff: AipMessage | None = None
