"""KnowFlow 解析队列看门狗。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.knowflow_queue_watchdog_service import (
    evaluate_knowflow_queue_watchdog,
    is_knowflow_queue_stuck,
)


def test_is_knowflow_queue_stuck_requires_backlog_and_idle_executor():
    metrics = {
        "enabled": True,
        "available": True,
        "pending_tasks": 5,
        "executor_active": False,
        "queue_lag": 2,
        "parsing_documents": 0,
    }
    with patch("app.services.knowflow_queue_watchdog_service.get_settings") as gs:
        gs.return_value = MagicMock(knowflow_queue_watchdog_min_pending=1)
        assert is_knowflow_queue_stuck(metrics) is True

    metrics["executor_active"] = True
    with patch("app.services.knowflow_queue_watchdog_service.get_settings") as gs:
        gs.return_value = MagicMock(knowflow_queue_watchdog_min_pending=1)
        assert is_knowflow_queue_stuck(metrics) is False


def test_watchdog_triggers_cmd_after_stuck_threshold():
    import app.services.knowflow_queue_watchdog_service as mod

    mod._stuck_since = None
    mod._last_recovery_at = 0.0
    metrics = {
        "enabled": True,
        "available": True,
        "pending_tasks": 9,
        "executor_active": False,
        "queue_lag": 2,
        "parsing_documents": 0,
    }
    settings = MagicMock(
        knowflow_enabled=True,
        knowflow_queue_watchdog_enabled=True,
        knowflow_queue_watchdog_stuck_minutes=10,
        knowflow_queue_watchdog_min_pending=1,
        knowflow_queue_watchdog_recovery_cooldown_sec=1800,
        knowflow_queue_watchdog_cmd="echo heal",
        knowflow_queue_watchdog_cmd_timeout_sec=60,
        knowflow_queue_watchdog_internal_recovery=False,
    )
    with (
        patch("app.services.knowflow_queue_watchdog_service.get_settings", return_value=settings),
        patch("app.services.knowflow_queue_watchdog_service.subprocess.run") as run,
    ):
        out = evaluate_knowflow_queue_watchdog(metrics, now=1000.0)
        assert out["stuck"] is True
        assert out["recovered"] is False

        out = evaluate_knowflow_queue_watchdog(metrics, now=1000.0 + 601.0)
        assert out["recovered"] is True
        run.assert_called_once()
