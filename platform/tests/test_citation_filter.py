"""引用展示过滤：对齐 KnowFlow 仅展示回答中引用的条目。"""

from __future__ import annotations

from app.services.knowledge_qa_service import (
    collapse_answer_citation_refs,
    filter_citations_for_display,
    merge_nearby_retrieval_hits,
)


def _cites(n: int):
    return [
        {
            "index": i + 1,
            "document_id": f"doc-{i}",
            "title": f"文档{i}",
            "snippet": f"片段{i}",
            "score": 1.0 - i * 0.1,
        }
        for i in range(n)
    ]


def test_filter_by_answer_citation_marks():
    citations = _cites(5)
    out = filter_citations_for_display(citations, "结论见 [1] 与 [3]。", max_fallback=5)
    assert [c["index"] for c in out] == [1, 3]


def test_fallback_without_body_refs_returns_empty():
    citations = [
        {"index": 1, "document_id": "a", "score": 0.9},
        {"index": 2, "document_id": "a", "score": 0.8},
        {"index": 3, "document_id": "b", "score": 0.7},
        {"index": 4, "document_id": "c", "score": 0.6},
    ]
    out = filter_citations_for_display(citations, "无编号回答", max_fallback=3)
    assert out == []


def test_collapse_same_document_keeps_highest_score():
    citations = [
        {
            "index": 2,
            "document_id": "a",
            "score": 0.92,
            "anchor_json": {"page": 3, "bbox": [10, 20, 100, 40]},
        },
        {
            "index": 3,
            "document_id": "a",
            "score": 0.61,
            "anchor_json": {"page": 5, "bbox": [12, 22, 102, 42]},
        },
    ]
    answer, out = collapse_answer_citation_refs("要点如下 [2][3]。", citations)
    assert answer == "要点如下 [2]。"
    assert [c["index"] for c in out] == [2]


def test_collapse_multi_document_keeps_each_document():
    citations = [
        {"index": 1, "document_id": "a", "score": 0.9},
        {"index": 2, "document_id": "b", "score": 0.85},
        {"index": 3, "document_id": "a", "score": 0.7},
    ]
    answer, out = collapse_answer_citation_refs("综合结论 [1][2][3]。", citations)
    assert answer == "综合结论 [1][2]。"
    assert [c["index"] for c in out] == [1, 2]


def test_collapse_same_page_citation_group():
    citations = [
        {
            "index": 2,
            "document_id": "a",
            "score": 0.88,
            "anchor_json": {"page": 3, "bbox": [10, 20, 100, 40]},
        },
        {
            "index": 3,
            "document_id": "a",
            "score": 0.55,
            "anchor_json": {"page": 3, "bbox": [12, 22, 102, 42]},
        },
    ]
    answer, out = collapse_answer_citation_refs("要点如下 [2][3]。", citations)
    assert answer == "要点如下 [2]。"
    assert [c["index"] for c in out] == [2]


def test_merge_nearby_retrieval_hits():
    hits = [
        {
            "document_id": "a",
            "score": 0.7,
            "anchor_json": {"page": 1, "bbox": [0, 0, 10, 10]},
        },
        {
            "document_id": "a",
            "score": 0.9,
            "anchor_json": {"page": 1, "bbox": [1, 1, 11, 11]},
        },
        {
            "document_id": "b",
            "score": 0.8,
            "anchor_json": {"page": 2, "bbox": [0, 0, 10, 10]},
        },
    ]
    merged = merge_nearby_retrieval_hits(hits)
    assert len(merged) == 2
    assert merged[0]["score"] == 0.9
    assert merged[1]["document_id"] == "b"
