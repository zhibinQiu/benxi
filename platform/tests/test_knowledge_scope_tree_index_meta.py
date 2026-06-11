"""知识检索树：索引状态与文档中心对齐、文档去重。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowledge_scope_tree_service import _ragflow_row_for_document


def test_enrich_doc_rows_meta_delegates_to_unified_reader():
    from app.services.knowledge_scope_tree_service import _enrich_doc_rows_meta

    db = MagicMock()
    user = MagicMock()
    doc_id = str(uuid.uuid4())
    rows = [{"document_id": doc_id, "parse_status": "解析中"}]
    documents = [MagicMock(id=uuid.UUID(doc_id))]

    with patch(
        "app.services.document_index_service.enrich_knowledge_document_rows",
    ) as enrich:
        _enrich_doc_rows_meta(db, user, "ds-1", rows, documents=documents)
    enrich.assert_called_once_with(db, user, rows, documents)


def test_ragflow_row_uses_canonical_link_without_dataset_id_equality():
    db = MagicMock()
    doc = MagicMock()
    doc.id = uuid.uuid4()
    dataset_id = "ds-personal"

    version_link = MagicMock()
    version_link.ragflow_document_id = "rag-new"

    with patch(
        "app.services.knowledge_scope_tree_service.document_matches_dataset_link",
        return_value=True,
    ), patch(
        "app.services.ragflow_sync_service.get_document_link",
        return_value=MagicMock(ragflow_document_id="rag-old"),
    ), patch(
        "app.services.ragflow_version_link_service.resolve_index_link",
        return_value=(version_link, MagicMock()),
    ):
        row = _ragflow_row_for_document(db, doc, dataset_id)

    assert row is not None
    assert row["ragflow_document_id"] == "rag-new"
    assert row["document_id"] == str(doc.id)
