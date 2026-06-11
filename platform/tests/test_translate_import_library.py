"""翻译结果入库测试。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.job import Job, JobStatus, JobType
from app.services.translate_service import import_job_to_library


def _done_job(**payload) -> Job:
    return Job(
        id=uuid.uuid4(),
        type=JobType.pdf_translate.value,
        status=JobStatus.done.value,
        created_by=uuid.uuid4(),
        payload={
            "pdf2zh_job_id": "remote-1",
            "file_name": "paper.pdf",
            "lang_in": "en",
            "lang_out": "zh-CN",
            **payload,
        },
    )


def test_import_translate_requires_done_status():
    job = _done_job()
    job.status = JobStatus.running.value
    db = MagicMock()
    user = MagicMock()
    try:
        import_job_to_library(db, user, job)
        assert False, "expected error"
    except Exception as e:
        assert "尚未完成" in str(e)


def test_import_translate_creates_document():
    job = _done_job()
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_id = uuid.uuid4()

    doc = MagicMock()
    doc.id = doc_id
    doc.title = "paper（译文 简体中文）"
    doc.deleted_at = None

    with patch(
        "app.services.translate_service._fetch_translate_output_bytes",
        return_value=(b"%PDF-1.4", "mono.pdf"),
    ), patch(
        "app.services.document_service.create_document",
        return_value=doc,
    ) as create_doc, patch(
        "app.services.document_service.create_initial_uploaded_version"
    ), patch(
        "app.services.translate_service._enqueue_knowledge_sync",
        return_value=True,
    ):
        db.refresh = MagicMock()
        result = import_job_to_library(db, user, job, variant="mono")

    create_doc.assert_called_once()
    assert result["document_id"] == doc_id
    assert result["already_imported"] is False
    assert result["knowflow_synced"] is True
    assert job.payload["imported_document_id"] == str(doc_id)


def test_import_translate_returns_existing_document():
    existing = uuid.uuid4()
    job = _done_job(imported_document_id=str(existing), imported_variant="mono")
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    doc = MagicMock()
    doc.id = existing
    doc.title = "已有文档"
    doc.deleted_at = None

    with patch(
        "app.services.document_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.translate_service._enqueue_knowledge_sync",
        return_value=True,
    ):
        result = import_job_to_library(db, user, job)

    assert result["already_imported"] is True
    assert result["document_id"] == existing
