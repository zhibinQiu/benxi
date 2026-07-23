"""语义层决策上下文 — 平台侧接线验证。"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.agent_planner import _rule_plan_for_platform_system_data
from app.services.agent_skill_router import (
    is_person_org_affiliation_question,
    is_platform_system_data_message,
)
from app.services.retrieval_priority import DEFAULT_RETRIEVAL_TOOL_ORDER
from app.benxi_semantic.intents import detect_intent_tags, tools_for_intents
from app.benxi_semantic.models import AgentDecisionContext, MatchedEntity


def test_retrieval_order_kg_before_ontology():
    assert DEFAULT_RETRIEVAL_TOOL_ORDER[0] == "kg_query"
    assert DEFAULT_RETRIEVAL_TOOL_ORDER[-1] == "ontology_query"


def test_affiliation_decision_prefers_kg_query():
    q = "邱智斌是哪个公司的？"
    assert is_person_org_affiliation_question(q)
    assert is_platform_system_data_message(q)
    tags = detect_intent_tags(q)
    preferred, blocked = tools_for_intents(tags)
    assert "kg_query" in preferred
    assert "web_search" in blocked

    plan = _rule_plan_for_platform_system_data(MagicMock(), MagicMock(), q)
    assert plan is not None
    assert "kg_query" in plan.allowed_tools


def test_agent_decision_context_structure_for_affiliation_answer():
    """决策上下文应能承载「所属组织」线索供规划/作答。"""
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="p1", name="邱智斌", type_code="person", score=103.0)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  所属组织: 海颐软件\n"
            "  关联:\n"
            "  → [任职于/member_of] → 海颐软件\n"
        ),
        intent_tags=["person_affiliation"],
        preferred_tools=["kg_query"],
        blocked_tools=["web_search", "knowledge_retrieve"],
        has_material=True,
        confidence=0.85,
        relation_count=1,
        entity_count=2,
    )
    assert ctx.has_material
    assert "海颐软件" in ctx.abox_snippets
    assert "kg_query" in ctx.preferred_tools
    plan_text = ctx.planning_text()
    assert "person_affiliation" in plan_text or "优先工具" in plan_text
