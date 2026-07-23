"""专精 hop 工具执行后是否继续轮次。"""

from __future__ import annotations

from app.services.agent_planner import SKILL_MGMT_INTENT, _fallback_plan, _make_plan
from app.services.agent_tool_loop import specialist_needs_more_rounds_after_tools


def test_carbon_stops_after_tool_outcomes():
    plan = _fallback_plan("处理用户请求")
    assert (
        specialist_needs_more_rounds_after_tools(
            agent_id="carbon",
            execution_plan=plan,
            loop_state={"tool_outcome_lines": ["carbon_policy：已获取 4 个政策数据源摘要"]},
        )
        is False
    )


def test_carbon_continues_without_outcomes():
    plan = _fallback_plan("处理用户请求")
    assert (
        specialist_needs_more_rounds_after_tools(
            agent_id="carbon",
            execution_plan=plan,
            loop_state={},
        )
        is True
    )


def test_skill_dev_continues_after_outcomes():
    plan = _make_plan(
        reasoning="技能开发",
        intent=SKILL_MGMT_INTENT,
        source="specialist",
    )
    assert (
        specialist_needs_more_rounds_after_tools(
            agent_id="skill-dev",
            execution_plan=plan,
            loop_state={"tool_outcome_lines": ["create_skill：已创建"]},
        )
        is True
    )


def test_assist_request_forces_more_rounds():
    plan = _fallback_plan("处理用户请求")
    assert (
        specialist_needs_more_rounds_after_tools(
            agent_id="carbon",
            execution_plan=plan,
            loop_state={"tool_outcome_lines": ["carbon_policy：完成"]},
            assist_request={"reason": "需要浏览器"},
        )
        is True
    )
