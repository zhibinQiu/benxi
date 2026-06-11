"""文档知识库索引后台任务。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.job import JobStatus, JobType
from app.services.knowledge_sync_job_service import (
    create_document_knowledge_index_job,
    enqueue_document_knowledge_index,
    schedule_knowledge_index_after_upload,
)


def test_create_document_knowledge_index_job_when_disabled():
    db = MagicMock()
    with patch(
        "app.services.knowledge_sync_job_service.knowledge.enabled",
        return_value=False,
    ):
        assert (
            create_document_knowledge_index_job(
                db,
                user_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
            )
            is None
        )


def test_create_document_knowledge_index_job_payload():
    db = MagicMock()
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job = MagicMock()
    job.id = uuid.uuid4()

    doc = MagicMock()
    doc.title = "测试文档"

    with patch(
        "app.services.knowledge_sync_job_service.knowledge.enabled",
        return_value=True,
    ), patch(
        "app.services.knowledge_sync_job_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.knowledge_sync_job_service.create_job",
        return_value=job,
    ) as create_job:
        out = create_document_knowledge_index_job(
            db,
            user_id=user_id,
            document_id=document_id,
            version_id=version_id,
        )

    assert out is job
    create_job.assert_called_once()
    kwargs = create_job.call_args.kwargs
    assert kwargs["job_type"] == JobType.document_index.value
    assert kwargs["created_by"] == user_id
    assert kwargs["document_id"] == document_id
    assert kwargs["payload"]["document_title"] == "测试文档"
    assert kwargs["payload"]["version_id"] == str(version_id)


def test_enqueue_document_knowledge_index_starts_thread():
    db = MagicMock()
    job = MagicMock()
    job.id = uuid.uuid4()

    with patch(
        "app.services.knowledge_sync_job_service.create_document_knowledge_index_job",
        return_value=job,
    ), patch(
        "app.services.knowledge_sync_job_service._start_job_thread"
    ) as start:
        out = enqueue_document_knowledge_index(
            db,
            user_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
        )

    assert out is job
    start.assert_called_once_with(job.id)


def test_schedule_knowledge_index_after_upload_delegates():
    db = MagicMock()
    job = MagicMock()
    job.id = uuid.uuid4()

    with patch(
        "app.services.knowledge_sync_job_service.enqueue_document_knowledge_index",
        return_value=job,
    ) as enqueue:
        out = schedule_knowledge_index_after_upload(
            db,
            user_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
        )

    assert out is job
    enqueue.assert_called_once()
    assert "force" in enqueue.call_args.kwargs
