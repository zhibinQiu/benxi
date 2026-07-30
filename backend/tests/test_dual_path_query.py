"""双路径：本体引导命中 / SQL 回退 / 答问校验。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.semantic.models import (
    AgentDecisionContext,
    FieldBinding,
    MatchedEntity,
    QueryPlan,
    ResolvedConcept,
    SqlPlanStep,
)
from app.semantic.ontology.answers import (
    answer_addresses_question,
    try_direct_answer_from_decision,
)
from app.semantic.ontology.field_mapper import FieldMapper
from app.semantic.ontology.path_planner import PathPlanner


def test_expand_concepts_via_relations_adds_peer_types():
    concepts = [
        ResolvedConcept(type_code="org", label="组织", relation_codes=["employs"])
    ]
    expanded = FieldMapper.expand_concepts_via_relations(concepts)
    codes = {c.type_code for c in expanded}
    assert "org" in codes
    assert "person" in codes


def test_map_concepts_registers_person_org_join():
    mapper = FieldMapper()
    concepts = FieldMapper.expand_concepts_via_relations(
        [ResolvedConcept(type_code="org", label="部门")]
    )
    bindings = mapper.map_concepts(concepts)
    join = [b for b in bindings if b.join_template == "person_org"]
    assert join, "扩展 person 后应注册 person_org 联查"


def test_path_planner_builds_join_sql_step():
    planner = PathPlanner()
    concepts = [
        ResolvedConcept(type_code="person", label="人员"),
        ResolvedConcept(type_code="org", label="组织"),
    ]
    bindings = [
        FieldBinding(
            concept="person",
            property_key="department",
            source="sql",
            join_template="person_org",
            notes="联查",
        )
    ]
    plan = planner.plan(
        "邱智斌是哪个部门的？",
        concepts=concepts,
        bindings=bindings,
        matched=[],
        owner_id="",
    )
    assert any(s.join_template == "person_org" for s in plan.sql_steps)


def test_answer_gate_rejects_contact_when_goal_is_department():
    plan = QueryPlan(
        question="邱智斌是哪个部门的？",
        concepts=[ResolvedConcept(type_code="person"), ResolvedConcept(type_code="org")],
        field_bindings=[
            FieldBinding(
                concept="person",
                property_key="department",
                source="sql",
                join_template="person_org",
            )
        ],
    )
    assert (
        answer_addresses_question(
            "邱智斌是哪个部门的？",
            "手机 17865569900 · 邮箱 a@b.com",
            plan=plan,
            snippets="描述: 手机 17865569900",
        )
        is False
    )


def test_answer_gate_accepts_department_from_sql():
    plan = QueryPlan(
        question="邱智斌是哪个部门的？",
        field_bindings=[
            FieldBinding(
                concept="person",
                property_key="department",
                source="sql",
                join_template="person_org",
            )
        ],
    )
    snippets = "[SQL person_org] 共 1 行\n- display_name=邱智斌; department_name=智碳产品分部"
    assert (
        answer_addresses_question(
            "邱智斌是哪个部门的？",
            "邱智斌属于智碳产品分部。",
            plan=plan,
            snippets=snippets,
        )
        is True
    )


def test_try_direct_answer_from_sql_snippets():
    ctx = AgentDecisionContext(
        matched_entities=[],
        abox_snippets=(
            "## 事务库属性（受控只读）\n"
            "[SQL person_org] 共 1 行\n"
            "- display_name=邱智斌; department_name=智碳产品分部\n"
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
            ]
        ),
    )
    reply = try_direct_answer_from_decision(ctx, "邱智斌是哪个部门的？")
    assert reply is not None
    assert "智碳产品分部" in reply
    assert "17865569900" not in (reply or "")


def test_try_direct_answer_from_employs_rel_not_contact_desc():
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  描述: 手机 17865569900 · 邮箱 a@b.com · 账号 邱智斌\n"
            "  所属组织: 智碳产品分部\n"
            "  关联:\n"
            "  → [任职/employs] → 智碳产品分部\n"
        ),
        preferred_tools=["kg_query"],
        has_material=True,
        confidence=0.85,
        query_plan=QueryPlan(
            concepts=[
                ResolvedConcept(type_code="person", relation_codes=["member_of"]),
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
