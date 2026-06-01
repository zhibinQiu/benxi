"""KnowFlow 同步应覆盖「可查询」全集（含分享），而非文档库列表过滤。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.document import Document


def test_sync_accessible_uses_queryable_list():
    from app.services.ragflow_sync_service import sync_accessible_documents

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = Document(id=uuid.uuid4(), title="shared-doc", scope="personal")

    with patch(
        "app.services.ragflow_sync_service.list_queryable_documents"
    ) as list_q, patch(
        "app.services.ragflow_sync_service._get_link", return_value=None
    ), patch(
        "app.services.ragflow_sync_service.sync_document_to_knowflow",
        return_value="rag-1",
    ) as sync_one:
        list_q.return_value = ([doc], 1)
        out = sync_accessible_documents(db, user, limit=10)

    list_q.assert_called()
    sync_one.assert_called_once_with(db, user, doc)
    assert out[str(doc.id)] == "rag-1"


def test_sync_accessible_refreshes_grants_when_link_exists():
    from app.services.ragflow_sync_service import sync_accessible_documents

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = Document(id=uuid.uuid4(), title="indexed", scope="company")
    link = MagicMock()

    with patch(
        "app.services.ragflow_sync_service.list_queryable_documents",
        return_value=([doc], 1),
    ), patch(
        "app.services.ragflow_sync_service._get_link", return_value=link
    ), patch(
        "app.services.ragflow_sync_service.sync_document_kb_grants"
    ) as refresh, patch(
        "app.services.ragflow_sync_service.sync_document_to_knowflow"
    ) as sync_one:
        sync_accessible_documents(db, user, limit=10)

    refresh.assert_called_once_with(db, doc)
    sync_one.assert_not_called()
