"""通用图谱直答判定与 UI 规划摘要。"""

from __future__ import annotations

from app.agent.loop.plan import AgentExecutionPlan
from app.semantic.ontology.answers import (
    can_answer_from_decision,
    try_direct_answer_from_decision,
)
from app.semantic.models import AgentDecisionContext, MatchedEntity
from app.semantic.kg.query_engine import question_match_tokens
from app.services.agent_planner import execution_plan_summary_for_ui


def test_question_match_tokens_extracts_names():
    tokens = question_match_tokens("邱智斌是哪个部门的")
    assert "邱智斌" in tokens


def test_can_answer_requires_confidence_and_material():
    weak = AgentDecisionContext(has_material=True, confidence=0.2, abox_snippets="x" * 20)
    assert can_answer_from_decision(weak) is False

    empty = AgentDecisionContext(
        has_material=True,
        confidence=0.9,
        abox_snippets="【知识图谱】未匹配到相关实体。",
        preferred_tools=["kg_query"],
    )
    assert can_answer_from_decision(empty) is False


def test_try_direct_answer_generic_high_confidence():
    from app.semantic.models import QueryPlan, FieldBinding

    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n[1] 人员 · 邱智斌\n  所属组织: 咨询服务部\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.85,
        query_plan=QueryPlan(
            field_bindings=[
                FieldBinding(
                    concept="person",
                    property_key="department",
                    source="sql",
                    join_template="person_org",
                )
            ],
        ),
    )
    assert can_answer_from_decision(ctx) is True
    reply = try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的")
    assert reply is not None
    assert "邱智斌" in reply
    assert "咨询服务部" in reply


def test_multi_facet_question_answers_all_parts():
    """一问多目标：手机 + 部门 + 公司，须分面合并，不能只答部门。"""
    from app.semantic.models import QueryPlan, FieldBinding
    from app.semantic.ontology.answers import detect_asked_facets

    q = "邱智斌的手机号是多少？是哪个部门的？是哪个公司的？"
    assert detect_asked_facets(q) == ["phone", "department", "company"]

    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  描述: 手机 17865569900 · 邮箱 a@b.com · 账号 邱智斌\n"
            "  所属组织: 智碳产品分部\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.85,
        query_plan=QueryPlan(
            field_bindings=[
                FieldBinding(
                    concept="person",
                    property_key="phone",
                    source="sql",
                    table="users",
                    column="phone",
                ),
                FieldBinding(
                    concept="person",
                    property_key="department",
                    source="sql",
                    join_template="person_org",
                ),
            ],
        ),
    )
    reply = try_direct_answer_from_decision(ctx, q)
    assert reply is not None
    assert "17865569900" in reply
    assert "智碳产品分部" in reply
    assert "手机" in reply


def test_try_direct_answer_from_employs_rel_not_contact_desc():
    """无「所属组织」行、仅有 employs 关联时，应答部门而非手机描述。"""
    from app.semantic.models import QueryPlan, ResolvedConcept, FieldBinding

    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  描述: 手机 17865569900 · 邮箱 a@b.com · 账号 邱智斌\n"
            "  关联:\n"
            "  → [任职/employs] → 智碳产品分部\n"
            "  ← [任职/inverse_of_employs] [推理] ← 智碳产品分部\n"
            "\n"
            "[2] 组织 · 智碳产品分部\n"
            "  ← [任职/employs] ← 邱智斌\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.85,
        query_plan=QueryPlan(
            concepts=[
                ResolvedConcept(type_code="person", relation_codes=["employs"]),
                ResolvedConcept(type_code="org"),
            ],
            field_bindings=[
                FieldBinding(
                    concept="person",
                    property_key="department",
                    source="sql",
                    join_template="person_org",
                )
            ],
        ),
    )
    reply = try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的？")
    assert reply is not None
    assert "智碳产品分部" in reply
    assert "17865569900" not in reply


def test_affiliation_without_org_does_not_dump_phone():
    from app.semantic.models import QueryPlan, FieldBinding

    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  描述: 手机 17865569900 · 邮箱 a@b.com · 账号 邱智斌\n"
        ),
        intent_tags=["person_affiliation"],
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.85,
        query_plan=QueryPlan(
            field_bindings=[
                FieldBinding(
                    concept="person",
                    property_key="department",
                    source="sql",
                    join_template="person_org",
                )
            ],
        ),
    )
    assert try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的？") is None


def test_try_direct_answer_skips_low_confidence():
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n[1] 人员 · 邱智斌\n  所属组织: 咨询服务部\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.3,
    )
    assert try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的") is None


def test_try_direct_answer_from_liked_memory():
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(
                id="m1",
                name="万斯相比德桑蒂斯有哪些优劣势",
                type_code="memory",
                score=80,
                description="万斯优势在年轻；德桑蒂斯短板在争议。",
            )
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 记忆 · 万斯相比德桑蒂斯有哪些优劣势\n"
            "  描述: 万斯优势在年轻；德桑蒂斯短板在争议。\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.5,
    )
    assert can_answer_from_decision(ctx) is True
    reply = try_direct_answer_from_decision(ctx, "万斯和德桑蒂斯谁更有优势")
    assert reply is not None
    assert "万斯" in reply


def test_execution_plan_summary_dedupes_same_intent_and_step():
    plan = AgentExecutionPlan(
        reasoning="处理用户请求",
        intent="处理用户请求",
        direct_answer=False,
        allowed_tools=(),
        blocked_tools=(),
        uploaded_skill=None,
        steps=("处理用户请求",),
        source="fallback",
    )
    summary = execution_plan_summary_for_ui(plan)
    assert summary.count("处理用户请求") == 1
