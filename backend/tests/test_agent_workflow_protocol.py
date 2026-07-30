"""Agent 流式协议：thinking → planning → executing（含并行波次）。"""

from __future__ import annotations

from app.agent.orchestrate.events import workflow_plan_tasks, workflow_task_event
from app.agent.orchestrate.protocol import (
    STAGE_EXECUTING,
    STAGE_PLANNING,
    STAGE_THINKING,
    enrich_workflow_data,
    format_reasoning_line,
    resolve_stage,
)
from app.agent.orchestrate.types import OrchestratorTask


def test_phase_to_stage_cycle():
    assert resolve_stage("agent_thinking") == STAGE_THINKING
    assert resolve_stage("plan_tasks") == STAGE_PLANNING
    assert resolve_stage("task_started") == STAGE_EXECUTING
    assert resolve_stage("tool_call", explicit="executing") == STAGE_EXECUTING
    assert resolve_stage("unknown") == ""


def test_enrich_workflow_data_sets_stage():
    data = enrich_workflow_data({"phase": "plan_tasks", "title": "Plan"})
    assert data["stage"] == STAGE_PLANNING


def test_format_reasoning_cycle_and_parallel():
    assert format_reasoning_line({"phase": "agent_thinking"}) == "[thinking]\n"
    assert format_reasoning_line(
        {"phase": "plan_tasks", "detail": "A ∥ B"}
    ) == "[planning] A ∥ B\n"

    a = OrchestratorTask(id="a", title="查碳价", agent_id="x", reason="", status="running")
    b = OrchestratorTask(id="b", title="查政策", agent_id="y", reason="", status="running")
    ev = workflow_task_event(
        "task_started",
        a,
        step_id="s1",
        all_tasks=[a, b],
        mode="parallel",
    )["data"]
    line = format_reasoning_line(ev)
    assert line.startswith("[executing:parallel]")
    assert "查碳价" in line and "查政策" in line

    solo = OrchestratorTask(id="a", title="单任务", agent_id="x", reason="", status="running")
    solo_ev = workflow_task_event(
        "task_started",
        solo,
        step_id="s2",
        all_tasks=[solo],
        mode="dag",
    )["data"]
    solo_line = format_reasoning_line(solo_ev)
    assert solo_line.startswith("[executing]")
    assert "parallel" not in solo_line
    assert "单任务" in solo_line


def test_plan_tasks_parallel_detail_uses_parallel_sep():
    tasks = [
        OrchestratorTask(id="1", title="A", agent_id="x", reason=""),
        OrchestratorTask(id="2", title="B", agent_id="y", reason=""),
    ]
    data = workflow_plan_tasks(tasks, step_id="p1", mode="parallel")["data"]
    assert data["stage"] == STAGE_PLANNING
    assert data["mode"] == "parallel"
    assert "∥" in data["detail"]
