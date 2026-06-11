"""重新索引 API 走后台任务。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.job import JobType
from app.services.knowledge_library_service import reindex_document


def test_reindex_document_enqueues_background_job():
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()

    doc = MagicMock(id=doc_id, deleted_at=None, title="测试文档")
    version = MagicMock(id=version_id, version_no=2)

    job = MagicMock(id=job_id)

    with patch(
        "app.services.knowledge_library_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.knowledge_library_service.can_query_document",
        return_value=True,
    ), patch(
        "app.domains.knowledge.gateway.knowledge.enabled",
        return_value=True,
    ), patch(
        "app.domains.knowledge.gateway.knowledge.stack_reachable",
        return_value=True,
    ), patch(
        "app.services.ragflow_version_link_service.resolve_index_link",
        return_value=(None, version),
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_reindex",
        return_value=job,
    ) as enqueue:
        result = reindex_document(
            db,
            user,
            doc_id,
            version_id=version_id,
            parser_id="smart",
            resync=True,
        )

    assert result["queued"] is True
    assert result["knowledge_job_id"] == str(job_id)
    assert result["version_id"] == str(version_id)
    enqueue.assert_called_once()
    kwargs = enqueue.call_args.kwargs
    assert kwargs["document_id"] == doc_id
    assert kwargs["version_id"] == version_id
    assert kwargs["resync"] is True
    assert kwargs["parser_id"] == "smart"
