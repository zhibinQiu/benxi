"""app.benxi_semantic 意图与决策上下文单测（纯函数 / 无 Neo4j）。"""

from __future__ import annotations

from app.benxi_semantic.intents import (
    INTENT_PERSON_AFFILIATION,
    detect_intent_tags,
    is_person_org_affiliation_question,
    tools_for_intents,
)
from app.benxi_semantic.models import AgentDecisionContext, MatchedEntity


def test_detect_person_affiliation_intent():
    tags = detect_intent_tags("邱智斌是哪个公司的？")
    assert INTENT_PERSON_AFFILIATION in tags
    assert is_person_org_affiliation_question("邱智斌是哪个公司的？")


def test_tools_for_affiliation_prefer_kg():
    preferred, blocked = tools_for_intents([INTENT_PERSON_AFFILIATION])
    assert "kg_query" in preferred
    assert "web_search" in blocked


def test_decision_context_planning_text():
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets="【知识图谱推理上下文】\n[1] 人员 · 邱智斌\n  所属组织: 海颐软件\n",
        tbox_compact="【本体摘要】\n- person (人员)\n- org (组织)",
        intent_tags=["person_affiliation"],
        preferred_tools=["kg_query"],
        blocked_tools=["web_search"],
        confidence=0.8,
        has_material=True,
    )
    text = ctx.planning_text()
    assert "优先工具" in text
    assert "kg_query" in text
    assert "海颐软件" in text or "邱智斌" in text
