"""知识库索引任务：解析等待与失败信息。"""

from __future__ import annotations

from contextlib import ExitStack
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.knowledge_sync_job_service import (
    _advance_parse_job_progress,
    _format_parse_failure,
    _is_retriable_parse_failure,
    _wait_for_parse,
)


def test_retriable_parse_failure_detection():
    assert _is_retriable_parse_failure("Page(1~13): OCR timeout")
    assert _is_retriable_parse_failure("服务繁忙")
    assert not _is_retriable_parse_failure("Model disabled")
    assert not _is_retriable_parse_failure("API 返回 403 Model disabled")


def test_format_parse_failure_includes_ragflow_detail():
    msg = _format_parse_failure("解析失败", "Page(1~13): OCR timeout")
    assert "解析失败" in msg
    assert "OCR timeout" in msg


def test_advance_parse_job_progress_unfreezes_stuck_ragflow_percent():
    progress, stagnant = _advance_parse_job_progress(
        68,
        status="解析中",
        rag_progress=68,
        stagnant_polls=0,
    )
    assert progress == 86
    assert stagnant == 0

    progress, stagnant = _advance_parse_job_progress(
        86,
        status="解析中",
        rag_progress=68,
        stagnant_polls=0,
    )
    assert progress == 86
    assert stagnant == 1

    progress, stagnant = _advance_parse_job_progress(
        86,
        status="解析中",
        rag_progress=68,
        stagnant_polls=1,
    )
    assert progress == 87
    assert stagnant == 0


def test_advance_parse_job_progress_when_status_unknown():
    progress, _ = _advance_parse_job_progress(
        68,
        status=None,
        rag_progress=None,
        stagnant_polls=0,
    )
    assert progress == 69


def _mock_parse_session(*, job, user, document):
    from app.models.job import Job
    from app.models.org import User

    db = MagicMock()

    def get(model, pk):
        if model is Job:
            return job
        if model is User:
            return user
        return None

    db.get.side_effect = get
    stack = ExitStack()
    stack.enter_context(
        patch(
            "app.services.knowledge_sync_job_service.get_document",
            return_value=document,
        )
    )
    stack.enter_context(patch("app.database.SessionLocal", return_value=db))
    return db, stack


def test_wait_for_parse_raises_on_failed_status_with_detail():
    job_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    user = MagicMock(id=user_id)
    job = MagicMock(id=job_id)
    document = MagicMock(id=document_id)

    db, stack = _mock_parse_session(job=job, user=user, document=document)
    with stack:
        with patch(
            "app.services.knowledge_sync_job_service._parse_run_status",
            return_value=("解析失败", None, -1, "Visual model error"),
        ), patch(
            "app.services.knowledge_sync_job_service.update_job_status",
        ), patch(
            "app.services.knowledge_sync_job_service._index_job_should_abort",
            return_value=False,
        ), patch(
            "app.services.knowledge_sync_job_service._maybe_retry_parse_failure",
            return_value=False,
        ):
            with pytest.raises(RuntimeError) as exc:
                _wait_for_parse(
                    job_id=job_id,
                    user_id=user_id,
                    document_id=document_id,
                    dataset_id="ds",
                    ragflow_document_id="doc",
                    max_wait_sec=5,
                )
        assert "Visual model error" in str(exc.value)
        db.close.assert_called()


def test_wait_for_parse_defers_when_still_running_after_wait():
    job_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    user = MagicMock(id=user_id)
    job = MagicMock(id=job_id)
    document = MagicMock(id=document_id)
    tick = 0.0

    def fake_time():
        return tick

    def fake_sleep(sec):
        nonlocal tick
        tick += sec + 1

    db, stack = _mock_parse_session(job=job, user=user, document=document)
    with stack:
        with patch(
            "app.services.knowledge_sync_job_service._parse_run_status",
            return_value=("解析中", 0, 42, None),
        ), patch(
            "app.services.knowledge_sync_job_service.update_job_status",
        ), patch(
            "app.services.knowledge_sync_job_service._index_job_should_abort",
            return_value=False,
        ), patch(
            "app.services.knowledge_sync_job_service.time.time",
            fake_time,
        ), patch(
            "app.services.knowledge_sync_job_service.time.sleep",
            fake_sleep,
        ):
            out = _wait_for_parse(
                job_id=job_id,
                user_id=user_id,
                document_id=document_id,
                dataset_id="ds",
                ragflow_document_id="doc",
                max_wait_sec=3,
                update_progress=False,
            )
        assert out is False
