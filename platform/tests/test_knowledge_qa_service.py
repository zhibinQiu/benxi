"""知识检索问答服务。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowledge_qa_service import (
    _filter_hits_by_version,
    _resolve_hit_platform_document_id,
    _strip_meta_footer,
    build_aligned_qa_context_and_citations,
    build_citations,
    finalize_citations_preserving_index,
    finalize_qa_answer_and_citations,
    generate_answer,
)

PLATFORM_DOC_ID = "11111111-1111-4111-8111-111111111111"
RAGFLOW_DOC_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_strip_meta_footer_removes_wrong_retrieval_note():
    text = "要点如下 [1]\n\n以上内容来自本地关键词检索；知识服务就绪后可获得语义检索能力。"
    out = _strip_meta_footer(text)
    assert "本地关键词检索" not in out
    assert "[1]" in out


def test_build_citations_includes_image_and_chunk():
    hits = [
        {
            "document_id": "11111111-1111-4111-8111-111111111111",
            "snippet": "片段",
            "highlight": "<em>片段</em>",
            "score": 0.88,
            "chunk_id": "chunk-1",
            "dataset_id": "ds-1",
            "img_id": "kb-abc123",
            "anchor_json": {"page": 2, "bbox": [10, 20, 30, 40]},
        }
    ]
    cites = build_citations(hits, {"11111111-1111-4111-8111-111111111111": "测试文档"}, question="体检通知")
    assert len(cites) == 1
    assert cites[0]["index"] == 1
    assert cites[0]["image_id"] == "kb-abc123"
    assert cites[0]["preview_available"] is True
    assert cites[0]["highlight_terms"]
    assert cites[0]["chunk_id"] == "chunk-1"
    assert cites[0]["anchor_json"]["page"] == 2


def test_build_citations_synthesizes_image_id_when_chunk_ids_present():
    hits = [
        {
            "document_id": "11111111-1111-4111-8111-111111111111",
            "snippet": "片段",
            "highlight": "片段",
            "content": "片段",
            "score": 0.5,
            "chunk_id": "chunk-1",
            "dataset_id": "ds-1",
            "ragflow_document_id": "rag-1",
        }
    ]
    cites = build_citations(hits, {"11111111-1111-4111-8111-111111111111": "测试"})
    assert cites[0]["image_id"] == "ds-1-chunk-1"
    assert cites[0]["preview_available"] is True


def test_build_citations_pageindex_page_preview():
    from app.services.knowledge_qa_service import _citation_preview_available

    hits = [
        {
            "document_id": "11111111-1111-4111-8111-111111111111",
            "snippet": "节点文本",
            "content": "节点文本",
            "source": "pageindex",
            "anchor_json": {},
            "preview_available": True,
        }
    ]
    meta = {
        "11111111-1111-4111-8111-111111111111": {
            "file_name": "报告.pdf",
            "file_format": "pdf",
        }
    }
    cites = build_citations(
        hits,
        {"11111111-1111-4111-8111-111111111111": "测试文档"},
        doc_meta=meta,
    )
    assert cites[0]["preview_available"] is True
    assert cites[0]["source"] == "pageindex"
    assert cites[0]["file_name"] == "报告.pdf"
    assert cites[0]["file_format"] == "pdf"
    assert cites[0]["anchor_json"] == {}
    assert _citation_preview_available(hits[0]) is True


def test_generate_answer_no_hits():
    answer = generate_answer(question="问题", hits=[], doc_titles={})
    assert "未找到" in answer
    assert "本地关键词" not in answer


def test_build_aligned_qa_context_skips_empty_and_reindexes():
    hits = [
        {"document_id": "d1", "content": "第一段", "score": 0.9},
        {"document_id": "d2", "content": "", "score": 0.8},
        {"document_id": "d3", "snippet": "第三段", "score": 0.7},
    ]
    ctx, cites = build_aligned_qa_context_and_citations(
        hits,
        {"d1": "A", "d2": "B", "d3": "C"},
        question="测试",
    )
    assert "[1]" in ctx and "第一段" in ctx
    assert "[2]" in ctx and "第三段" in ctx
    assert "[3]" not in ctx
    assert "《" not in ctx
    assert len(cites) == 2
    assert cites[0]["index"] == 1
    assert cites[1]["index"] == 2
    assert cites[1]["title"] == "C"


def test_finalize_qa_preserves_citation_index():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
        {"index": 3, "document_id": "c", "title": "Doc C", "snippet": "gamma"},
    ]
    answer = "要点 [1]。补充 [3]。"
    normalized, kept = finalize_qa_answer_and_citations(answer, citations)
    assert "[1]" in normalized and "[3]" in normalized
    assert len(kept) == 2
    assert kept[0]["index"] == 1
    assert kept[1]["index"] == 3


def test_finalize_qa_keeps_all_citations_without_marks():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
    ]
    answer = "根据材料，项目将于下月启动。"
    normalized, kept = finalize_qa_answer_and_citations(answer, citations)
    assert "项目将于下月启动" in normalized
    assert len(kept) == 2
    assert [c["index"] for c in kept] == [1, 2]


def test_finalize_citations_strips_reference_section():
    raw = "结论 [1]。\n\n## 参考来源\n- 文档A"
    answer, kept = finalize_citations_preserving_index(
        raw,
        [{"index": 1, "document_id": "a", "title": "A", "snippet": "x"}],
    )
    assert "参考来源" not in answer
    assert "结论" in answer
    assert len(kept) == 1


def test_resolve_hit_platform_document_id_from_ragflow_map():
    allowed = {PLATFORM_DOC_ID}
    vmap = {
        RAGFLOW_DOC_ID: {
            "platform_document_id": PLATFORM_DOC_ID,
            "document_version_id": None,
        }
    }
    hit = {"ragflow_document_id": RAGFLOW_DOC_ID, "document_id": RAGFLOW_DOC_ID}
    pid = _resolve_hit_platform_document_id(hit, allowed, vmap)
    assert pid == PLATFORM_DOC_ID


def test_filter_hits_by_version_maps_ragflow_doc_to_platform():
    user = MagicMock()
    db = MagicMock()
    doc = MagicMock()
    doc.id = uuid.UUID(PLATFORM_DOC_ID)

    hits = [
        {
            "ragflow_document_id": RAGFLOW_DOC_ID,
            "document_id": RAGFLOW_DOC_ID,
            "snippet": "命中片段",
            "highlight": "<em>命中</em>片段",
            "image_id": "img-1",
            "score": 0.9,
        }
    ]

    with patch(
        "app.services.knowledge_qa_service.ragflow_to_platform_version_map",
        return_value={
            RAGFLOW_DOC_ID: {
                "platform_document_id": PLATFORM_DOC_ID,
                "document_version_id": None,
            }
        },
    ), patch(
        "app.services.knowledge_qa_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.knowledge_qa_service.resolve_latest_indexed_version",
        return_value=None,
    ), patch(
        "app.services.knowledge_qa_service.resolve_current_version",
        return_value=None,
    ):
        out = _filter_hits_by_version(
            db,
            user,
            hits,
            [uuid.UUID(PLATFORM_DOC_ID)],
        )

    assert len(out) == 1
    assert out[0]["document_id"] == PLATFORM_DOC_ID
    assert out[0]["image_id"] == "img-1"
