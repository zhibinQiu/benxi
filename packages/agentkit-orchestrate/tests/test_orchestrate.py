"""agentkit-orchestrate 单元测试。"""

from __future__ import annotations

from agentkit_orchestrate import (
    AssistRules,
    OrchestratorTask,
    VerifyHooks,
    VerifyRules,
    assess_answer_coverage_rule,
    build_deliverable_brief,
    build_global_round_reflection,
    build_helper_assist_message,
    resolve_assist_agent_id,
    should_escalate_to_skill_dev,
    tasks_from_routes,
    verify_task_result,
)


class _Route:
    def __init__(self, agent_id: str, reason: str):
        self.agent_id = agent_id
        self.reason = reason


def _verify_hooks() -> VerifyHooks:
    def is_substantive(text: str) -> bool:
        return len(text.strip()) > 20 and "已读取" not in text

    def looks_like_denial(text: str) -> bool:
        return "无法" in text or "抱歉" in text

    return VerifyHooks(
        is_substantive_deliverable=is_substantive,
        reply_looks_like_denial=looks_like_denial,
    )


_VERIFY_RULES = VerifyRules(action_agent_ids=frozenset({"platform"}))
_ASSIST_RULES = AssistRules(
    assistable_agent_ids=frozenset({"platform", "research", "skill-dev"}),
    no_escalate_agent_ids=frozenset({"skill-dev", "orchestrator"}),
    action_agent_ids=frozenset({"platform"}),
)


def test_tasks_from_routes():
    routes = [_Route("platform", "平台"), _Route("research", "检索")]
    tasks = tasks_from_routes(routes, title_fn=lambda a: a.upper())
    assert len(tasks) == 2
    assert tasks[0].title == "PLATFORM"


def test_verify_rejects_tool_failure():
    task = OrchestratorTask(id="t1", title="平台", agent_id="platform", reason="x")
    events = [
        {"type": "workflow", "data": {"phase": "tool_result", "status": "failed", "detail": "权限不足"}}
    ]
    ok, summary, hint = verify_task_result(
        task, events, {"reply": "失败"}, rules=_VERIFY_RULES, hooks=_verify_hooks()
    )
    assert ok is False
    assert not summary
    assert hint


def test_resolve_assist_from_suggestion():
    task = OrchestratorTask(id="t1", title="平台", agent_id="platform", reason="x")
    assist = {"suggested_agent_id": "research", "reason": "缺检索", "needed_from": "知识库"}
    assert resolve_assist_agent_id(assist, task, "用户问题", rules=_ASSIST_RULES) == "research"


def test_should_escalate_platform_without_tools():
    task = OrchestratorTask(
        id="t1",
        title="平台",
        agent_id="platform",
        reason="x",
        last_error="请调用平台工具",
    )
    assert should_escalate_to_skill_dev(task, satisfied=False, events=[], rules=_ASSIST_RULES) is True


def test_assess_rule_accepts_substantive():
    task = OrchestratorTask(
        id="t1",
        title="检索",
        agent_id="research",
        reason="x",
        summary="本文介绍了碳市场配额机制与近期政策调整要点。",
    )
    from agentkit_orchestrate.types import TaskExecutionResult

    result = TaskExecutionResult(task=task, route=_Route("research", "x"), satisfied=True)
    out = assess_answer_coverage_rule(
        "请总结这篇文章",
        [result],
        is_substantive_deliverable=lambda s: len(s) > 15 and "已读取" not in s,
    )
    assert out.addresses_user is True


def test_tool_failure_lines_collects_all():
    from agentkit_orchestrate.event_parse import tool_failure_lines_in_events

    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "failed",
                "tool_name": "invoke_skill",
                "detail": "参数无效：params",
            },
        },
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "failed",
                "tool": "run_skill_script",
                "detail": "缺少 main.py",
            },
        },
    ]
    lines = tool_failure_lines_in_events(events)
    assert len(lines) == 2
    assert "invoke_skill" in lines[0]
    from agentkit_orchestrate import OrchestratorAnswerAssessment
    from agentkit_orchestrate.types import TaskExecutionResult

    task = OrchestratorTask(id="t1", title="检索", agent_id="research", reason="x", summary="已读取 100 字")
    result = TaskExecutionResult(task=task, route=_Route("research", "x"), satisfied=True)
    assessment = OrchestratorAnswerAssessment(False, gap="尚未形成回答")
    text = build_global_round_reflection(
        global_round=0,
        assessment=assessment,
        results=[result],
        routing_context_line="涉及专精：research",
    )
    assert "第 1 轮全局验收未通过" in text
    assert "research" in text


def test_build_helper_message():
    task = OrchestratorTask(id="t1", title="报告", agent_id="report", reason="x")
    msg = build_helper_assist_message("写报告", task, {"reason": "缺材料", "needed_from": "知识库"})
    assert "调度协调" in msg
    assert "知识库" in msg


def test_build_deliverable_brief():
    from agentkit_orchestrate.types import TaskExecutionResult

    t1 = OrchestratorTask(id="t1", title="A", agent_id="a", reason="x", summary="完成内容")
    t2 = OrchestratorTask(id="t2", title="B", agent_id="b", reason="x", last_error="失败")
    results = [
        TaskExecutionResult(task=t1, route=_Route("a", "x"), satisfied=True),
        TaskExecutionResult(task=t2, route=_Route("b", "x"), satisfied=False),
    ]
    brief = build_deliverable_brief(results)
    assert "完成" in brief
    assert "未完成" in brief


async def test_iter_task_event_parts():
    from agentkit_orchestrate import ORCH_TASK_RESULT, iter_task_event_parts

    async def _stream():
        yield {"type": "workflow", "data": {"phase": "task_started"}}
        yield {"type": ORCH_TASK_RESULT, "result": {"ok": True}}

    kinds = []
    async for kind, _ in iter_task_event_parts(_stream()):
        kinds.append(kind)
    assert kinds == ["event", "result"]
