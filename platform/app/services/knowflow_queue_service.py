"""KnowFlow / RAGFlow 解析队列监控（MySQL task + Redis stream lag）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_QUEUE_NAMES = ("rag_flow_svr_queue", "rag_flow_svr_queue_1")
_CONSUMER_GROUP = "rag_flow_svr_task_broker"


def collect_knowflow_queue_metrics(db: Session | None = None) -> dict[str, Any]:
    """采集解析队列健康状态：是否卡住、积压与 executor 活跃度。"""
    from app.config import get_settings

    settings = get_settings()
    out: dict[str, Any] = {
        "enabled": bool(settings.knowflow_enabled),
        "available": False,
        "stuck": False,
        "watchdog_enabled": bool(
            settings.knowflow_enabled and settings.knowflow_queue_watchdog_enabled
        ),
        "watchdog_stuck_minutes": max(
            1, int(settings.knowflow_queue_watchdog_stuck_minutes)
        ),
        "pending_tasks": 0,
        "running_tasks": 0,
        "parsing_documents": 0,
        "queue_lag": 0,
        "executor_active": False,
        "top_backlog_documents": [],
        "error": None,
    }
    if not settings.knowflow_enabled:
        return out

    from app.services.model_settings_service import get_ragflow_mysql_settings

    _, password, db_name, host, port = get_ragflow_mysql_settings(db)
    if not password or not host:
        out["error"] = "未配置知识库 MySQL"
        return out

    try:
        import pymysql

        conn = pymysql.connect(
            host=host,
            port=port,
            user="root",
            password=password,
            database=db_name,
            charset="utf8mb4",
            connect_timeout=settings.ragflow_mysql_connect_timeout,
            read_timeout=settings.ragflow_mysql_read_timeout,
            write_timeout=settings.ragflow_mysql_write_timeout,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM task
                WHERE begin_at IS NULL AND progress >= 0 AND progress < 1
                """
            )
            out["pending_tasks"] = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT COUNT(*) FROM task
                WHERE begin_at IS NOT NULL AND progress >= 0 AND progress < 1
                """
            )
            out["running_tasks"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT COUNT(*) FROM document WHERE run = '1'")
            out["parsing_documents"] = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT d.name, COUNT(*) AS pending_cnt
                FROM task t
                JOIN document d ON d.id = t.doc_id
                WHERE t.begin_at IS NULL AND t.progress >= 0 AND t.progress < 1
                GROUP BY d.id, d.name
                ORDER BY pending_cnt DESC
                LIMIT 8
                """
            )
            out["top_backlog_documents"] = [
                {"name": row[0], "pending_tasks": int(row[1])}
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT MAX(begin_at) FROM task
                WHERE begin_at IS NOT NULL AND begin_at > NOW() - INTERVAL 1 HOUR
                """
            )
            recent = cur.fetchone()[0]
            out["executor_active"] = bool(recent) or out["running_tasks"] > 0
        conn.close()
        out["available"] = True
    except Exception as exc:
        logger.debug("KnowFlow 队列指标采集失败: %s", exc)
        from app.core.user_messages import sanitize_user_message

        out["error"] = sanitize_user_message(
            str(exc)[:200], fallback="知识库队列指标采集失败"
        )
        return out

    try:
        import redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        total_lag = 0
        for q in _QUEUE_NAMES:
            try:
                groups = client.xinfo_groups(q)
            except Exception:
                continue
            for g in groups:
                if g.get("name") == _CONSUMER_GROUP:
                    total_lag += int(g.get("lag") or 0)
                    break
        out["queue_lag"] = total_lag
    except Exception as exc:
        logger.debug("Redis 队列 lag 采集失败: %s", exc)
        if not out.get("error"):
            out["error"] = f"Redis: {exc}"[:200]

    from app.services.knowflow_queue_watchdog_service import is_knowflow_queue_stuck

    out["stuck"] = is_knowflow_queue_stuck(out)
    return out
