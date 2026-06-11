"""知识检索问答服务。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowledge_qa_service import (
    _filter_hits_by_version,
    _resolve_hit_platform_document_id,
    _strip_meta_footer,
    build_citations,
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
            "image_id": "kb-abc123",
            "anchor_json": {"page": 2, "bbox": [10, 20, 30, 40]},
        }
    ]
    cites = build_citations(hits, {"11111111-1111-4111-8111-111111111111": "测试文档"})
    assert len(cites) == 1
    assert cites[0]["index"] == 1
    assert cites[0]["image_id"] == "kb-abc123"
    assert cites[0]["chunk_id"] == "chunk-1"
    assert cites[0]["anchor_json"]["page"] == 2


def test_generate_answer_no_hits():
    answer = generate_answer(question="问题", hits=[], doc_titles={})
    assert "未找到" in answer
    assert "本地关键词" not in answer


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
