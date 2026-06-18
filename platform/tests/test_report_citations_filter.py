"""报告引用过滤工具测试。"""

from __future__ import annotations

from app.services.report_generation_service import finalize_report_citations


def test_finalize_report_citations_renumbers_to_sequential():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
        {"index": 4, "document_id": "d", "title": "Doc D", "snippet": "delta"},
    ]
    answer = "结论一 [1]。\n\n结论二 [4]。"
    normalized, kept = finalize_report_citations(answer, citations)
    assert normalized == "结论一 [1]。\n\n结论二 [2]。"
    assert [c["index"] for c in kept] == [1, 2]


def test_finalize_report_citations_drops_unused_when_body_has_no_refs():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
    ]
    answer = "## 背景\n报告正文未标注引用编号。"
    _, kept = finalize_report_citations(answer, citations)
    assert kept == []
