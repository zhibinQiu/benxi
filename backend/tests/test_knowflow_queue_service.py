"""KnowFlow 解析队列指标。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.knowflow_queue_service import (
    _normalize_document_base_name,
    collect_knowflow_queue_metrics,
)


def test_normalize_document_base_name():
    assert _normalize_document_base_name("report(12).pdf") == "report.pdf"
    assert _normalize_document_base_name("黄金(3).pdf") == "黄金.pdf"


def test_collect_knowflow_queue_metrics_disabled():
    with patch("app.config.get_settings") as gs:
        gs.return_value = MagicMock(knowflow_enabled=False)
        out = collect_knowflow_queue_metrics()
    assert out["enabled"] is False
    assert out["pending_tasks"] == 0
