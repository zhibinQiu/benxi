"""通用图谱直答判定与 UI 规划摘要。"""

from __future__ import annotations

from app.agentkit.loop.plan import AgentExecutionPlan
from app.benxi_semantic.answers import (
    can_answer_from_decision,
    try_direct_answer_from_decision,
)
from app.benxi_semantic.models import AgentDecisionContext, MatchedEntity
from app.benxi_semantic.query_engine import question_match_tokens
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
    )
    assert can_answer_from_decision(ctx) is True
    reply = try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的")
    assert reply is not None
    assert "邱智斌" in reply
    assert "咨询服务部" in reply


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
