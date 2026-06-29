"""专精智能体 execution plan 收窄测试。"""

from __future__ import annotations

from app.core.report_skill_catalog import REPORT_SKILL_SURVEY
from app.services.agent_planner import AgentExecutionPlan
from app.services.agent_skill_router import MERMAID_DIAGRAM_SKILL
from app.services.agent_tool_loop import _narrow_execution_plan_for_specialist


def test_diagram_specialist_forces_mermaid_skill():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="日常交流",
        direct_answer=True,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="test",
    )
    narrowed = _narrow_execution_plan_for_specialist(
        plan,
        agent_id="diagram",
        allowed_skill_names={MERMAID_DIAGRAM_SKILL},
    )
    assert narrowed.uploaded_skill == MERMAID_DIAGRAM_SKILL
    assert narrowed.direct_answer is False
    assert MERMAID_DIAGRAM_SKILL in narrowed.steps[0]


def test_allowed_skills_strip_unknown_upload():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="other-skill",
        builtin_orchestration=None,
        steps=(),
        source="test",
    )
    narrowed = _narrow_execution_plan_for_specialist(
        plan,
        agent_id="diagram",
        allowed_skill_names={MERMAID_DIAGRAM_SKILL},
    )
    assert narrowed.uploaded_skill == MERMAID_DIAGRAM_SKILL


def test_report_specialist_picks_survey_skill():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="",
        direct_answer=True,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="test",
    )
    narrowed = _narrow_execution_plan_for_specialist(
        plan,
        agent_id="report",
        allowed_skill_names={REPORT_SKILL_SURVEY},
        user_message="撰写新能源汽车行业调研报告",
    )
    assert narrowed.uploaded_skill == REPORT_SKILL_SURVEY
    assert narrowed.direct_answer is False
    assert "knowledge_retrieve" in narrowed.atomic_tools
