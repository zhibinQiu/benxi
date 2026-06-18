"""文档中心格式概览统计。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.document_overview_service import collect_document_format_overview


def _doc(*, doc_id=None, current_version_id=None):
    return MagicMock(
        id=doc_id or uuid.uuid4(),
        current_version_id=current_version_id,
    )


def test_collect_overview_groups_by_format_and_parsed():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    pdf_doc = _doc()
    word_doc = _doc()
    pdf_ver_id = uuid.uuid4()
    word_ver_id = uuid.uuid4()
    pdf_doc.current_version_id = pdf_ver_id
    word_doc.current_version_id = word_ver_id

    pdf_ver = MagicMock(id=pdf_ver_id, file_name="a.pdf", mime_type="application/pdf")
    word_ver = MagicMock(
        id=word_ver_id,
        file_name="b.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    with patch(
        "app.services.document_overview_service.filter_accessible_documents",
        return_value=[pdf_doc, word_doc],
    ), patch(
        "app.services.document_overview_service.enrich_document_index_meta",
        return_value={
            str(pdf_doc.id): {"knowledge_synced": True, "parse_status": "已索引"},
            str(word_doc.id): {"knowledge_synced": True, "parse_status": "未解析"},
        },
    ):
        db.scalars.return_value.all.return_value = [pdf_ver, word_ver]
        out = collect_document_format_overview(db, user, scope="personal")

    assert out["total"] == 2
    assert out["parsed_total"] == 1
    by_fmt = {item["format"]: item for item in out["items"]}
    assert by_fmt["pdf"]["total"] == 1
    assert by_fmt["pdf"]["parsed"] == 1
    assert by_fmt["word"]["total"] == 1
    assert by_fmt["word"]["parsed"] == 0


def test_collect_overview_empty():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    with patch(
        "app.services.document_overview_service.filter_accessible_documents",
        return_value=[],
    ):
        out = collect_document_format_overview(db, user, scope="personal")
    assert out == {"items": [], "total": 0, "parsed_total": 0}
