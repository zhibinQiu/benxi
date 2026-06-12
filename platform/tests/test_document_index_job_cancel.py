"""删除文档/版本时终止后台索引任务并清理 KnowFlow 映射。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.job import Job, JobStatus, JobType
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.knowledge_sync_job_service import (
    _index_job_should_abort,
    _index_target_exists,
    cancel_document_index_job,
    stop_document_index_work,
)
from app.services.ragflow_sync_service import detach_platform_version_knowflow


def test_stop_document_index_work_cancels_running_job():
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        document_id=document_id,
        created_by=uuid.uuid4(),
        payload={
            "document_id": str(document_id),
            "version_id": str(version_id),
            "awaiting_parse": True,
        },
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [job]

    with patch(
        "app.services.knowledge_sync_job_service.update_job_status",
        return_value=job,
    ) as update_status:
        stopped = stop_document_index_work(db, document_id, version_id=version_id)

    assert stopped == 1
    update_status.assert_called_once()
    assert update_status.call_args.args[2] == JobStatus.cancelled.value
    assert job.payload.get("awaiting_parse") is None


def test_cancel_document_index_job_clears_parse_watch():
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.done.value,
        document_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        payload={
            "awaiting_parse": True,
            "parse_watch_started_at": 1.0,
            "dataset_id": "ds-1",
        },
    )
    db = MagicMock()

    with patch(
        "app.services.knowledge_sync_job_service.update_job_status",
        return_value=job,
    ) as update_status:
        out = cancel_document_index_job(db, job)

    assert out is job
    assert job.payload.get("awaiting_parse") is None
    assert job.payload.get("parse_watch_started_at") is None
    update_status.assert_called_once()
    assert update_status.call_args.args[2] == JobStatus.cancelled.value


def test_index_job_should_abort_reads_cancelled_from_db():
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        document_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        payload={},
    )
    fresh = Job(
        id=job.id,
        type=job.type,
        status=JobStatus.cancelled.value,
        document_id=job.document_id,
        created_by=job.created_by,
        payload={},
    )
    db = MagicMock()
    db.get.return_value = fresh

    assert _index_job_should_abort(db, job) is True
    assert job.status == JobStatus.cancelled.value


def test_index_job_should_abort_when_version_missing():
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        document_id=document_id,
        created_by=uuid.uuid4(),
        payload={"version_id": str(version_id)},
    )
    doc = Document(
        id=document_id,
        title="t",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
    )

    def fake_get(model, pk):
        if model is Job:
            return job
        if model is Document:
            return doc
        if model is DocumentVersion:
            return None
        return None

    db = MagicMock()
    db.get = fake_get

    assert _index_job_should_abort(db, job) is True


def test_detach_platform_version_knowflow_deletes_link_and_schedules_remote():
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        title="t",
        owner_id=user_id,
        scope="personal",
        status=DocumentStatus.active.value,
    )
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_no=1,
        file_name="a.pdf",
        file_key="docs/x",
        file_size=10,
        created_by=user_id,
    )
    vl = RagflowDocumentVersionLink(
        id=uuid.uuid4(),
        platform_document_id=doc_id,
        platform_version_id=version_id,
        version_no=1,
        platform_user_id=user_id,
        ragflow_document_id="rag-v1",
        dataset_id="ds-1",
        file_name="a.pdf",
        index_completed_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=vl,
    ), patch(
        "app.services.ragflow_version_link_service.count_ragflow_document_references",
        return_value=0,
    ), patch(
        "app.services.ragflow_sync_service._get_link",
        return_value=None,
    ), patch(
        "app.services.ragflow_sync_service._execute_knowflow_deletes",
    ) as execute_deletes:
        targets = detach_platform_version_knowflow(
            db, document, version, sync_remote=True
        )

    assert len(targets) == 1
    assert targets[0].ragflow_document_id == "rag-v1"
    db.delete.assert_called_once_with(vl)
    execute_deletes.assert_called_once()


def test_index_target_exists_requires_version():
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    other_version_id = uuid.uuid4()
    doc = Document(
        id=document_id,
        title="t",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
    )
    ver = DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_no=1,
        created_by=uuid.uuid4(),
    )

    def fake_get(model, pk):
        if model is Document:
            return doc
        if model is DocumentVersion:
            if pk == version_id:
                return ver
            return None
        return None

    db = MagicMock()
    db.get = fake_get

    assert _index_target_exists(db, document_id, version_id) is True
    assert _index_target_exists(db, document_id, other_version_id) is False
