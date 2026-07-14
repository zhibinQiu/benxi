"""KnowFlow / RAGFlow 解析队列监控（MySQL task + Redis stream lag）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_QUEUE_NAMES = ("rag_flow_svr_queue", "rag_flow_svr_queue_1")
_CONSUMER_GROUP = "rag_flow_svr_task_broker"


def _classify_mysql_error(exc: Exception, host: str, port: int) -> str:
    """将 MySQL 异常分类为用户可读的简短描述（不暴露密码/堆栈）。"""
    msg = str(exc).lower()
    if "access denied" in msg or "1045" in msg:
        return "知识库 MySQL 账号或密码错误"
    if "unknown database" in msg or "1049" in msg:
        return "知识库数据库名（rag_flow）不存在"
    if "can't connect" in msg or "connection refused" in msg or "2003" in msg:
        return f"知识库 MySQL 服务不可达（{host}:{port}），请确认容器已启动"
    if "timeout" in msg or "timed out" in msg:
        return f"知识库 MySQL 连接超时（{host}:{port}）"
    if "no route to host" in msg or "113" in msg:
        return f"知识库 MySQL 网络不可达（{host}），请检查网络/DNS"
    return "知识库 MySQL 连接异常"


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

    from app.integrations.mysql_conn import get_mysql_connection

    try:
        conn = get_mysql_connection(
            host=host,
            port=port,
            password=password,
            database=db_name,
            connect_timeout=5,
            read_timeout=8,
            write_timeout=10,
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
        logger.warning("KnowFlow 队列指标采集失败 (MySQL %s:%s): %s", host, port, exc)
        out["error"] = _classify_mysql_error(exc, host, port)
        return out

    try:
        import redis

        redis_timeout = max(0.5, float(settings.redis_socket_timeout_sec))
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=redis_timeout,
            socket_timeout=redis_timeout,
        )
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
        logger.warning("Redis 队列 lag 采集失败: %s", exc)
        if not out.get("error"):
            out["error"] = "知识库 Redis 连接异常"

    from app.services.knowflow_queue_watchdog_service import is_knowflow_queue_stuck

    out["stuck"] = is_knowflow_queue_stuck(out)
    return out
