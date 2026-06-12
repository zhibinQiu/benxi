"""知识库索引任务：解析等待与失败信息。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.knowledge_sync_job_service import (
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


def test_wait_for_parse_raises_on_failed_status_with_detail():
    db = MagicMock()
    user = MagicMock()
    job = MagicMock()
    job.id = "job-1"

    with patch(
        "app.services.knowledge_sync_job_service._parse_run_status",
        return_value=("解析失败", None, -1, "Visual model error"),
    ), patch(
        "app.services.knowledge_sync_job_service.update_job_status",
    ):
        with pytest.raises(RuntimeError) as exc:
            _wait_for_parse(
                db,
                user,
                job,
                dataset_id="ds",
                ragflow_document_id="doc",
                document=MagicMock(),
                max_wait_sec=5,
            )
    assert "Visual model error" in str(exc.value)


def test_wait_for_parse_defers_when_still_running_after_wait():
    db = MagicMock()
    user = MagicMock()
    job = MagicMock()
    job.id = "job-2"
    tick = 0.0

    def fake_time():
        return tick

    def fake_sleep(sec):
        nonlocal tick
        tick += sec + 1

    with patch(
        "app.services.knowledge_sync_job_service._parse_run_status",
        return_value=("解析中", 0, 42, None),
    ), patch(
        "app.services.knowledge_sync_job_service.update_job_status",
    ), patch(
        "app.services.knowledge_sync_job_service.time.time",
        fake_time,
    ), patch(
        "app.services.knowledge_sync_job_service.time.sleep",
        fake_sleep,
    ):
        doc = MagicMock()
        out = _wait_for_parse(
            db,
            user,
            job,
            dataset_id="ds",
            ragflow_document_id="doc",
            document=doc,
            max_wait_sec=3,
            update_progress=False,
        )
    assert out is False
