"""Workflow 事件构造 — 前端/流式协议层。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent.orchestrate.protocol import (
    STAGE_EXECUTING,
    STAGE_PLANNING,
    enrich_workflow_data,
)
from app.agent.orchestrate.types import OrchestratorTask


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
    orchestrator_label: str = "orchestrator",
    detail: str | None = None,
    edges: list[dict[str, str]] | None = None,
    plan_title: str = "Plan",
) -> dict[str, Any]:
    if mode in ("parallel", "dag") and len(tasks) > 1:
        chain = " ∥ ".join(t.title for t in tasks)
    else:
        chain = " → ".join(t.title for t in tasks)
    resolved_detail = detail if detail is not None else (chain or f"{len(tasks)} 个任务")
    data: dict[str, Any] = {
        "phase": "plan_tasks",
        "stage": STAGE_PLANNING,
        "title": "任务规划" if plan_title == "Plan" else plan_title,
        "detail": resolved_detail,
        "tool": "supervisor.plan",
        "step_id": step_id,
        "mode": mode,
        "tasks": [task_to_json(t) for t in tasks],
        "agent_id": orchestrator_title,
        "agent_title": orchestrator_label,
    }
    if edges:
        data["edges"] = edges
    return {"type": "workflow", "data": enrich_workflow_data(data)}


def workflow_task_event(
    phase: str,
    task: OrchestratorTask,
    *,
    step_id: str,
    detail: str = "",
    attempt: int | None = None,
    all_tasks: list[OrchestratorTask] | None = None,
    agent_title_fn: Callable[[str], str] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    title_fn = agent_title_fn or (lambda agent_id: agent_id)
    snapshot = all_tasks if all_tasks is not None else [task]
    running_n = sum(1 for t in snapshot if t.status == "running")
    resolved_mode = mode or ("parallel" if running_n > 1 else "sequential")
    data: dict[str, Any] = {
        "phase": phase,
        "stage": STAGE_EXECUTING,
        "task_id": task.id,
        "title": task.title,
        "detail": detail[:240],
        "tool": "supervisor.task",
        "step_id": step_id,
        "mode": resolved_mode,
        "agent_id": task.agent_id,
        "agent_title": title_fn(task.agent_id),
        "tasks": [task_to_json(t) for t in snapshot],
    }
    if attempt is not None:
        data["attempt"] = attempt
    if phase in ("task_done", "task_failed"):
        data["status"] = "done" if phase == "task_done" else "failed"
    return {"type": "workflow", "data": enrich_workflow_data(data)}
