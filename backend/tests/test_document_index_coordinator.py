"""文档索引协调层：租约、阶段、入队幂等。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.job import Job, JobStatus, JobType
from app.services.document_index_coordinator import (
    INDEX_PHASE_AWAITING_PARSE,
    enter_awaiting_parse_phase,
    index_phase,
    is_awaiting_parse_phase,
    try_begin_execution,
)
from app.services.knowledge_sync_job_service import create_document_knowledge_index_job


def test_index_phase_reads_legacy_awaiting_parse_flag():
    assert index_phase({"awaiting_parse": True}) == INDEX_PHASE_AWAITING_PARSE
    assert index_phase({"index_phase": "full"}) == "full"


def test_enter_awaiting_parse_phase_sets_explicit_phase():
    out = enter_awaiting_parse_phase(
        {},
        dataset_id="ds-1",
        ragflow_document_id="rid-1",
        mode="index",
        version_id_raw="v-1",
    )
    assert out["index_phase"] == INDEX_PHASE_AWAITING_PARSE
    assert out["awaiting_parse"] is True
    assert is_awaiting_parse_phase(out)


def test_try_begin_execution_rejects_active_lease():
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        document_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        payload={"exec_lease_until": 9_999_999_999.0},
    )
    db = MagicMock()
    db.scalar.return_value = job

    assert try_begin_execution(db, job) is False


def test_create_document_knowledge_index_job_reuses_active_when_not_force():
    document_id = uuid.uuid4()
    existing = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        document_id=document_id,
        created_by=uuid.uuid4(),
        payload={"document_id": str(document_id), "force": False},
    )
    db = MagicMock()

    with patch(
        "app.services.knowledge_sync_job_service.find_active_document_index_job",
        return_value=existing,
    ), patch(
        "app.services.knowledge_sync_job_service._cancel_active_document_index_jobs",
    ) as cancel_jobs, patch(
        "app.services.knowledge_sync_job_service.create_job",
    ) as create_job:
        out = create_document_knowledge_index_job(
            db,
            user_id=existing.created_by,
            document_id=document_id,
            force=False,
        )

    assert out is existing
    cancel_jobs.assert_not_called()
    create_job.assert_not_called()
