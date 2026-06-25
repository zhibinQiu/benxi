"""父智能体任务编排验收逻辑。"""

from __future__ import annotations

from app.services.agent_orchestrator import (
    OrchestratorTask,
    tasks_from_routes,
    verify_task_result,
)
from app.services.agent_supervisor import AgentRoute


def test_tasks_from_routes_one_per_route():
    routes = [
        AgentRoute(agent_id="platform", reason="平台"),
        AgentRoute(agent_id="scheduler", reason="定时"),
    ]
    tasks = tasks_from_routes(routes)
    assert len(tasks) == 2
    assert tasks[0].id == "t1"
    assert tasks[0].agent_id == "platform"
    assert tasks[1].agent_id == "scheduler"


def test_verify_rejects_tool_failure():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "failed",
                "detail": "权限不足",
            },
        }
    ]
    ok, summary, hint = verify_task_result(task, events, {"reply": "失败了"})
    assert ok is False
    assert not summary
    assert "重试" in hint or "权限" in hint


def test_verify_accepts_tool_success_reply():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "done",
                "detail": "文件夹已创建",
            },
        }
    ]
    ok, summary, hint = verify_task_result(
        task, events, {"reply": "已在文档库创建文件夹「喝水」"}
    )
    assert ok is True
    assert "喝水" in summary
    assert not hint


def test_verify_rejects_excuse_without_tools():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    ok, _, hint = verify_task_result(
        task,
        [],
        {"reply": "小析无直接创建本地文件夹的工具，建议您手动新建"},
    )
    assert ok is False
    assert hint
