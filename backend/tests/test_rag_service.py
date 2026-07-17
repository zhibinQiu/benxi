"""知识问答会话：创建时不应自动触发文档索引。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services import rag_service


def test_sync_docs_to_knowflow_does_not_enqueue_index():
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_ready = MagicMock()
    doc_ready.id = uuid.uuid4()
    doc_ready.title = "已索引文档"
    doc_pending = MagicMock()
    doc_pending.id = uuid.uuid4()
    doc_pending.title = "待索引文档"
    docs = [doc_ready, doc_pending]

    mock_map = {str(doc_ready.id): "rag-1", str(doc_pending.id): "rag-2"}
    with patch(
        "app.services.ragflow_sync_service.allowed_ragflow_doc_map",
        return_value=mock_map,
    ):
        mapping = rag_service._sync_docs_to_knowflow(db, user, docs)

    assert mapping == mock_map
