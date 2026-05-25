"""KnowFlow 索引：删除平台文档时清理 RAGFlow 映射。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.document import Document, DocumentStatus
from app.models.ragflow_document_link import RagflowDocumentLink
from app.services.ragflow_sync_service import remove_platform_document_from_knowflow


def test_remove_platform_document_from_knowflow_deletes_link():
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="t",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
        deleted_at=datetime.now(timezone.utc),
    )
    link = RagflowDocumentLink(
        id=uuid.uuid4(),
        platform_document_id=doc_id,
        platform_user_id=uuid.uuid4(),
        ragflow_document_id="rag-1",
        dataset_id="ds-1",
        file_name="a.pdf",
    )
    db = MagicMock()
    db.scalar.return_value = link

    mock_client = MagicMock()
    mock_client.health_ok.return_value = True

    with patch(
        "app.services.ragflow_sync_service.RagflowClient",
        return_value=mock_client,
    ):
        assert remove_platform_document_from_knowflow(db, doc) is True

    mock_client.delete_documents.assert_called_once_with("ds-1", ["rag-1"])
    db.delete.assert_called_once_with(link)
