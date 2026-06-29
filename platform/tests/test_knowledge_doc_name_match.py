"""知识检索文档名/文件名匹配。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.knowledge_qa.doc_name_match import (
    extract_document_name_hints,
    resolve_retrieval_document_scope,
    score_document_name_match,
)


def test_extract_document_name_hints_from_quoted_and_file():
    hints = extract_document_name_hints("请总结《全国碳市场报告》的主要内容")
    assert "全国碳市场报告" in hints

    hints = extract_document_name_hints("采购合同.pdf 讲了什么")
    assert any("采购合同" in h for h in hints)


def test_extract_document_name_hints_from_doc_ref():
    hints = extract_document_name_hints("这份体检通知文件主要说了什么")
    assert any("体检通知" in h for h in hints)


def test_score_document_name_match_title_and_filename():
    assert score_document_name_match(
        "采购合同",
        title="采购管理制度",
        file_name="采购合同.pdf",
    ) >= 0.85
    assert score_document_name_match(
        "全国碳市场报告",
        title="全国碳市场报告",
        file_name="report-final.docx",
    ) == 1.0


def test_resolve_scope_when_question_mentions_selected_doc_title():
    doc_a = MagicMock(id=uuid.uuid4(), title="采购合同")
    doc_b = MagicMock(id=uuid.uuid4(), title="员工手册")
    file_names = {
        str(doc_a.id): "contract.pdf",
        str(doc_b.id): "handbook.pdf",
    }
    scoped = resolve_retrieval_document_scope(
        [doc_a, doc_b],
        file_names,
        "采购合同主要讲了什么？",
    )
    assert scoped == [doc_a]


def test_resolve_scope_when_keyword_in_filename():
    doc_a = MagicMock(id=uuid.uuid4(), title="制度汇编")
    doc_b = MagicMock(id=uuid.uuid4(), title="其他材料")
    file_names = {
        str(doc_a.id): "制度汇编.pdf",
        str(doc_b.id): "采购合同.pdf",
    }
    scoped = resolve_retrieval_document_scope(
        [doc_a, doc_b],
        file_names,
        "请说明采购合同中的付款条款",
    )
    assert scoped == [doc_b]


def test_resolve_scope_keeps_all_when_no_name_match():
    doc_a = MagicMock(id=uuid.uuid4(), title="年度报告")
    doc_b = MagicMock(id=uuid.uuid4(), title="季度简报")
    file_names = {
        str(doc_a.id): "annual.pdf",
        str(doc_b.id): "quarterly.pdf",
    }
    docs = [doc_a, doc_b]
    scoped = resolve_retrieval_document_scope(
        docs,
        file_names,
        "碳中和政策对行业有什么影响？",
    )
    assert scoped == docs
