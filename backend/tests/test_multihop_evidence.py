"""通用真多跳：路径格式化、workflow 证据、直答消费路径。"""

from __future__ import annotations

import asyncio

from app.semantic.kg.reasoning import (
    ReasoningEngine,
    _PlanResult,
    _format_path_text,
)
from app.semantic.models import (
    AgentDecisionContext,
    FieldBinding,
    MatchedEntity,
    QueryPlan,
)
from app.semantic.ontology.answers import (
    _company_from_evidence_paths,
    try_direct_answer_from_decision,
)
from app.services.semantic_workflow import (
    format_evidence_paths_detail,
    semantic_probe_done_events,
)


def test_format_path_text_readable():
    text = asyncio.run(
        _format_path_text(
            {
                "path_nodes": [
                    {"id": "1", "name": "邱智斌", "type_code": "person"},
                    {"id": "2", "name": "智碳产品分部", "type_code": "org"},
                    {"id": "3", "name": "本析科技", "type_code": "org"},
                ],
                "path_edges": [
                    {"type_code": "employs", "forward": False},
                    {"type_code": "part_of", "forward": True},
                ],
                "path_rels": ["employs", "part_of"],
            },
            relation_label_fn=None,
        )
    )
    assert text is not None
    assert "邱智斌" in text
    assert "<-[employs]-" in text
    assert "-[part_of]->" in text
    assert "本析科技" in text


def test_format_properties_line():
    from app.semantic.kg.reasoning import _format_properties_line

    assert "phone=178" in _format_properties_line({"phone": "178", "email": ""})
    assert _format_properties_line("{}") == ""
    assert "phone=1" in _format_properties_line('{"phone":"1"}')


def test_reasoning_format_emits_evidence_paths():
    engine = ReasoningEngine.__new__(ReasoningEngine)
    engine._entity_label_fn = None
    engine._relation_label_fn = None

    async def _entity_label(c: str) -> str:
        return {"person": "人员", "org": "组织"}.get(c, c)

    async def _relation_label(c: str) -> str:
        return {"employs": "任职", "part_of": "属于"}.get(c, c)

    engine._entity_label = _entity_label  # type: ignore[method-assign]
    engine._relation_label = _relation_label  # type: ignore[method-assign]

    class _Ops:
        async def collect(self, *_a, **_k):
            return [
                {
                    "id": "1",
                    "name": "邱智斌",
                    "type_code": "person",
                    "description": "手机 17865569900",
                },
                {
                    "id": "2",
                    "name": "智碳产品分部",
                    "type_code": "org",
                    "description": "",
                },
                {
                    "id": "3",
                    "name": "本析科技",
                    "type_code": "org",
                    "description": "",
                },
            ]

    engine._ops = _Ops()  # type: ignore[attr-defined]

    result = _PlanResult(
        contexts=[
            {
                "path_nodes": [
                    {"id": "1", "name": "邱智斌", "type_code": "person"},
                    {"id": "2", "name": "智碳产品分部", "type_code": "org"},
                    {"id": "3", "name": "本析科技", "type_code": "org"},
                ],
                "path_rels": ["employs", "part_of"],
                "hops": 2,
                "is_inferred": True,
                "source_id": "1",
                "target_id": "3",
                "rel_type": "employs",
            },
            {
                "source_id": "1",
                "source_name": "邱智斌",
                "source_type": "person",
                "target_id": "2",
                "target_name": "智碳产品分部",
                "target_type": "org",
                "rel_type": "employs",
                "hops": 1,
            },
        ],
        entity_ids={"1", "2", "3"},
        hops=2,
        inferred_entities=1,
    )
    matched = [MatchedEntity(id="1", name="邱智斌", type_code="person", score=100)]
    payload = asyncio.run(engine._format(result, matched))
    assert payload.evidence_paths
    assert "本析科技" in payload.evidence_paths[0]
    assert "【多跳证据路径】" in payload.context_text
    assert any(c.get("kind") == "kg_path" for c in payload.citations)


def test_semantic_probe_done_includes_paths():
    events = semantic_probe_done_events(
        "step-1",
        planning_text="问什么/为何: 查人员组织",
        direct=True,
        has_material=True,
        evidence_paths=[
            "邱智斌 -[任职/employs]-> 智碳产品分部 -[属于/part_of]-> 本析科技"
        ],
    )
    blob = "\n".join(str(e.get("detail") or "") for e in events)
    assert "证据路径" in blob
    assert "本析科技" in blob
    assert format_evidence_paths_detail(
        ["A -[r]-> B"]
    ).startswith("证据路径")


def test_company_from_multihop_path():
    company = _company_from_evidence_paths(
        ["邱智斌 -[任职/employs]-> 智碳产品分部 -[属于/part_of]-> 本析科技"],
        exclude_names=["邱智斌", "智碳产品分部"],
    )
    assert company == "本析科技"


def test_multi_facet_uses_path_company_not_dept():
    q = "邱智斌的手机号是多少？是哪个部门的？是哪个公司的？"
    ctx = AgentDecisionContext(
        matched_entities=[
            MatchedEntity(id="1", name="邱智斌", type_code="person", score=103)
        ],
        abox_snippets=(
            "【多跳证据路径】\n"
            "路径1 (2跳): 邱智斌 -[任职/employs]-> 智碳产品分部 -[属于/part_of]-> 本析科技\n\n"
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  描述: 手机 17865569900 · 邮箱 a@b.com\n"
            "  所属组织: 智碳产品分部\n"
        ),
        evidence_paths=[
            "邱智斌 -[任职/employs]-> 智碳产品分部 -[属于/part_of]-> 本析科技"
        ],
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
    assert "本析科技" in reply
    assert "公司" in reply
