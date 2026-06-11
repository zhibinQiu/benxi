"""知识库数据对账与上传索引 force 判据。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.knowledge_data_reconcile_service import (
    should_force_knowledge_index_after_upload,
)
from app.services.knowledge_sync_job_service import schedule_knowledge_index_after_upload
from app.services.ragflow_version_link_service import count_ragflow_document_references


def test_should_force_when_no_version_link():
    db = MagicMock()
    db.scalar.return_value = None
    assert (
        should_force_knowledge_index_after_upload(
            db, document_id=uuid.uuid4(), version_id=uuid.uuid4()
        )
        is True
    )


def test_should_not_force_when_version_indexed():
    db = MagicMock()
    version_id = uuid.uuid4()
    vl = MagicMock()
    vl.ragflow_document_id = "rag-1"
    vl.index_completed_at = datetime.now(timezone.utc)
    ver = MagicMock()
    ver.file_size = 1024
    db.scalar.return_value = vl
    db.get.return_value = ver

    with patch(
        "app.services.knowledge_data_reconcile_service.is_version_uploaded",
        return_value=True,
    ):
        assert (
            should_force_knowledge_index_after_upload(
                db, document_id=uuid.uuid4(), version_id=version_id
            )
            is False
        )


def test_count_ragflow_document_references_excludes_document():
    db = MagicMock()
    doc_id = uuid.uuid4()
    other_id = uuid.uuid4()
    vl_self = MagicMock(platform_document_id=doc_id, ragflow_document_id="r1")
    vl_other = MagicMock(platform_document_id=other_id, ragflow_document_id="r1")
    db.scalars.return_value.all.side_effect = [
        [vl_self],
        [],
        [],
    ]
    assert (
        count_ragflow_document_references(db, "r1", exclude_document_id=doc_id) == 1
    )


def test_schedule_upload_uses_force_false_when_indexed():
    db = MagicMock()
    job = MagicMock()
    job.id = uuid.uuid4()
    version_id = uuid.uuid4()

    with (
        patch(
            "app.services.knowledge_data_reconcile_service.should_force_knowledge_index_after_upload",
            return_value=False,
        ),
        patch(
            "app.services.knowledge_sync_job_service.enqueue_document_knowledge_index",
            return_value=job,
        ) as enqueue,
    ):
        out = schedule_knowledge_index_after_upload(
            db,
            user_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=version_id,
        )

    assert out is job
    assert enqueue.call_args.kwargs["force"] is False
