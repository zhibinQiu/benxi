"""报告引用过滤工具测试。"""

from __future__ import annotations

from app.services.report_generation_service import finalize_report_citations


def test_finalize_report_citations_only_keeps_used():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
    ]
    answer = "结论一 [1]。\n\n## 背景\n更多说明。"
    normalized, kept = finalize_report_citations(answer, citations)
    assert "[1]" in normalized
    assert len(kept) == 1
    assert kept[0]["index"] == 1


def test_finalize_report_citations_keeps_all_when_body_has_no_refs():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
    ]
    answer = "## 背景\n报告正文未标注引用编号。"
    _, kept = finalize_report_citations(answer, citations)
    assert len(kept) == 2
