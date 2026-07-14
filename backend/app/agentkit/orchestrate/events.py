"""Workflow 事件构造 — 前端/流式协议层。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agentkit.orchestrate.types import OrchestratorTask


def task_to_json(task: OrchestratorTask) -> dict[str, Any]:
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
    orchestrator_title: str = "orchestrator",
    orchestrator_label: str = "调度",
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
            "tasks": [task_to_json(t) for t in tasks],
            "agent_id": orchestrator_title,
            "agent_title": orchestrator_label,
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
    agent_title_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    title_fn = agent_title_fn or (lambda agent_id: agent_id)
    snapshot = all_tasks if all_tasks is not None else [task]
    data: dict[str, Any] = {
        "phase": phase,
        "task_id": task.id,
        "title": task.title,
        "detail": detail[:240],
        "tool": "supervisor.task",
        "step_id": step_id,
        "agent_id": task.agent_id,
        "agent_title": title_fn(task.agent_id),
        "tasks": [task_to_json(t) for t in snapshot],
    }
    if attempt is not None:
        data["attempt"] = attempt
    if phase in ("task_done", "task_failed"):
        data["status"] = "done" if phase == "task_done" else "failed"
    return {"type": "workflow", "data": data}
