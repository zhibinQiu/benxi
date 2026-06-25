"""父智能体任务编排 — 规划清单、顺序执行、验收与重试。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.agent_profiles import get_agent_profile

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


def workflow_plan_tasks(tasks: list[OrchestratorTask], *, step_id: str) -> dict[str, Any]:
    return {
        "type": "workflow",
        "data": {
            "phase": "plan_tasks",
            "title": "任务规划",
            "detail": f"共 {len(tasks)} 项",
            "tool": "supervisor.plan",
            "step_id": step_id,
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
    profile = get_agent_profile(agent_id)
    return profile.title if profile else agent_id


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


def verify_task_result(
    task: OrchestratorTask,
    events: list[dict[str, Any]],
    complete: dict[str, Any] | None,
) -> tuple[bool, str, str]:
    """规则验收：无工具失败且有条理结果即通过。返回 (satisfied, summary, retry_hint)。"""
    failed, fail_detail = _tool_failed_in_events(events)
    if failed:
        return (
            False,
            "",
            f"请修正后重试：{fail_detail}" if fail_detail else "上次工具调用失败，请换用正确工具重试",
        )

    reply = str((complete or {}).get("reply") or "").strip()
    citations = list((complete or {}).get("citations") or [])
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
