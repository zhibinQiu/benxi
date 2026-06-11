"""知识库索引任务：解析等待与失败信息。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.knowledge_sync_job_service import (
    _format_parse_failure,
    _wait_for_parse,
)


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
                timeout_sec=5,
            )
    assert "Visual model error" in str(exc.value)
