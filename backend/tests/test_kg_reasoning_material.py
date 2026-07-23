"""图谱材料判定与上下文合并。"""

from __future__ import annotations

from app.schemas.kg import KgQaContext
from app.services.kg_service import merge_kg_qa_into_context
from app.services.retrieval_priority import kg_has_material


def test_kg_has_material_rejects_empty_match_fallback():
    empty = KgQaContext(
        context_text="【知识图谱】未从问题中识别到具体实体，请提供更详细的问题。",
        entity_count=0,
    )
    assert kg_has_material(empty) is False

    blank = KgQaContext(context_text="", entity_count=100)
    assert kg_has_material(blank) is False


def test_kg_has_material_accepts_reasoning_context():
    ctx = KgQaContext(
        context_text=(
            "【知识图谱推理上下文】\n"
            "[1] 人员 · 邱智斌\n"
            "  所属组织: 海颐软件\n"
            "  关联:\n"
            "  → [任职于/member_of] → 海颐软件\n"
        ),
        matched_entity_ids=["e1"],
        entity_count=2,
        relation_count=1,
    )
    assert kg_has_material(ctx) is True


def test_merge_kg_qa_keeps_base_context():
    kg = KgQaContext(context_text="【知识图谱推理上下文】\n[1] 人员 · 邱智斌")
    merged = merge_kg_qa_into_context("文档片段A", [], kg)
    assert "文档片段A" in merged
    assert "邱智斌" in merged


def test_merge_kg_qa_legacy_db_user_form():
    kg = KgQaContext(context_text="【知识图谱推理上下文】\n[1] org · 海颐软件")
    merged = merge_kg_qa_into_context(None, None, kg, base_context="报告正文")
    assert "报告正文" in merged
    assert "海颐软件" in merged
