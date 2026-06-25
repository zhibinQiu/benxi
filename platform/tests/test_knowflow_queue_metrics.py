"""KnowFlow 队列指标 stuck 状态。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.knowflow_queue_service import collect_knowflow_queue_metrics


def test_collect_knowflow_queue_metrics_disabled_not_stuck():
    with patch("app.config.get_settings") as gs:
        settings = gs.return_value
        settings.knowflow_enabled = False
        settings.knowflow_queue_watchdog_enabled = True
        settings.knowflow_queue_watchdog_stuck_minutes = 10
        out = collect_knowflow_queue_metrics()
    assert out["enabled"] is False
    assert out["stuck"] is False


def test_collect_knowflow_queue_metrics_sets_stuck_flag():
    settings = MagicMock()
    settings.knowflow_enabled = True
    settings.knowflow_queue_watchdog_enabled = True
    settings.knowflow_queue_watchdog_stuck_minutes = 10
    settings.ragflow_mysql_connect_timeout = 5
    settings.ragflow_mysql_read_timeout = 5
    settings.ragflow_mysql_write_timeout = 5
    settings.redis_url = "redis://localhost:6379/0"

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        (3,),  # pending
        (0,),  # running
        (0,),  # parsing docs
        (None,),  # recent begin_at
    ]
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    with (
        patch("app.config.get_settings", return_value=settings),
        patch(
            "app.services.model_settings_service.get_ragflow_mysql_settings",
            return_value=("root", "pw", "rag_flow", "127.0.0.1", 3306),
        ),
        patch("pymysql.connect", return_value=conn),
        patch("redis.from_url") as redis_from_url,
        patch(
            "app.services.knowflow_queue_watchdog_service.is_knowflow_queue_stuck",
            return_value=True,
        ) as stuck_fn,
    ):
        redis_client = MagicMock()
        redis_client.xinfo_groups.return_value = [
            {"name": "rag_flow_svr_task_broker", "lag": 2}
        ]
        redis_from_url.return_value = redis_client
        out = collect_knowflow_queue_metrics()

    stuck_fn.assert_called_once()
    assert out["stuck"] is True
    assert out["pending_tasks"] == 3
    assert out["watchdog_enabled"] is True
