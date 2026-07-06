"""知识问答会话：创建时不应对已索引文档重复入队。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services import rag_service


def test_sync_docs_to_knowflow_skips_index_ready_documents():
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

    with patch(
        "app.services.ragflow_sync_service.allowed_ragflow_doc_map",
        return_value={str(doc_ready.id): "rag-1", str(doc_pending.id): "rag-2"},
    ), patch(
        "app.domains.knowledge.gateway.knowledge.enabled",
        return_value=True,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value={
            str(doc_ready.id): {
                "knowledge_synced": True,
                "parse_status": "已索引",
            },
            str(doc_pending.id): {
                "knowledge_synced": True,
                "parse_status": "解析中",
            },
        },
    ), patch(
        "app.services.document_service.resolve_current_version",
        return_value=None,
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_knowledge_index",
    ) as enqueue:
        mapping = rag_service._sync_docs_to_knowflow(db, user, docs)

    assert mapping[str(doc_ready.id)] == "rag-1"
    enqueue.assert_called_once()
    call_kw = enqueue.call_args.kwargs
    assert call_kw["document_id"] == doc_pending.id
    assert call_kw["force"] is False
