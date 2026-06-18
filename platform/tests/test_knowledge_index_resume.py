"""文档索引中断续跑。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.knowledge_sync_job_service import (
    KnowledgeIndexResumeResult,
    try_resume_incomplete_knowledge_index,
)


def test_resume_returns_none_without_version_link():
    db = MagicMock()
    user = MagicMock()
    doc = MagicMock()
    doc.id = uuid.uuid4()
    version = MagicMock()
    version.id = uuid.uuid4()

    with patch(
        "app.services.document_service.resolve_current_version",
        return_value=version,
    ), patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=None,
    ):
        assert (
            try_resume_incomplete_knowledge_index(db, user, doc, version_id=None)
            is None
        )


def test_resume_skips_when_index_already_completed_in_db():
    db = MagicMock()
    user = MagicMock()
    doc = MagicMock()
    version_id = uuid.uuid4()
    version = MagicMock()
    version.id = version_id
    vl = MagicMock()
    vl.ragflow_document_id = "rag-1"
    vl.dataset_id = "ds-1"
    vl.index_completed_at = datetime.now(timezone.utc)

    db.get.return_value = version
    with patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=vl,
    ):
        out = try_resume_incomplete_knowledge_index(
            db, user, doc, version_id=version_id
        )

    assert isinstance(out, KnowledgeIndexResumeResult)
    assert out.already_completed is True
    assert out.ragflow_document_id == "rag-1"


def test_resume_waits_when_parse_running():
    db = MagicMock()
    user = MagicMock()
    doc = MagicMock()
    version_id = uuid.uuid4()
    version = MagicMock()
    version.id = version_id
    version.file_name = "a.pdf"
    version.mime_type = "application/pdf"
    vl = MagicMock()
    vl.ragflow_document_id = "rag-2"
    vl.dataset_id = "ds-2"
    vl.index_completed_at = None
    vl.file_name = "a.pdf"

    db.get.return_value = version
    with patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=vl,
    ), patch(
        "app.services.knowledge_sync_job_service._parse_run_status",
        return_value=("解析中", 0, 42, None),
    ), patch(
        "app.services.ragflow_sync_service._configure_and_parse_uploaded_document",
    ) as reparse:
        out = try_resume_incomplete_knowledge_index(
            db, user, doc, version_id=version_id
        )

    assert out is not None
    assert out.already_completed is False
    reparse.assert_not_called()


def test_resume_does_not_retrigger_parse_on_failure():
    db = MagicMock()
    user = MagicMock()
    doc = MagicMock()
    version_id = uuid.uuid4()
    version = MagicMock()
    version.id = version_id
    version.file_name = "b.docx"
    version.mime_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    vl = MagicMock()
    vl.ragflow_document_id = "rag-3"
    vl.dataset_id = "ds-3"
    vl.index_completed_at = None
    vl.file_name = "b.docx"

    db.get.return_value = version
    with patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=vl,
    ), patch(
        "app.services.knowledge_sync_job_service._parse_run_status",
        return_value=("解析失败", 0, -1, "timeout"),
    ), patch(
        "app.services.knowledge_sync_job_service._retrigger_ragflow_parse",
    ) as reparse:
        out = try_resume_incomplete_knowledge_index(
            db, user, doc, version_id=version_id
        )

    assert out is not None
    assert out.already_completed is False
    reparse.assert_not_called()
