"""KnowFlow / RAGFlow 解析队列监控（MySQL task + Redis stream lag）。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_QUEUE_NAMES = ("rag_flow_svr_queue", "rag_flow_svr_queue_1")
_CONSUMER_GROUP = "rag_flow_svr_task_broker"
_DUP_SUFFIX_RE = re.compile(r"\(\d+\)(\.[^.]+)?$")


def _normalize_document_base_name(name: str | None) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    return _DUP_SUFFIX_RE.sub(lambda m: m.group(1) or "", text).strip()


def collect_knowflow_queue_metrics(db: Session | None = None) -> dict[str, Any]:
    """采集解析队列积压：pending task、解析中文档、Redis lag、重复上传概览。"""
    from app.config import get_settings

    settings = get_settings()
    out: dict[str, Any] = {
        "enabled": bool(settings.knowflow_enabled),
        "available": False,
        "pending_tasks": 0,
        "running_tasks": 0,
        "failed_tasks": 0,
        "parsing_documents": 0,
        "unstarted_documents": 0,
        "queue_lag": 0,
        "queue_lag_by_priority": {},
        "executor_active": False,
        "duplicate_document_groups": 0,
        "duplicate_documents_extra": 0,
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

            cur.execute("SELECT COUNT(*) FROM task WHERE progress = -1")
            out["failed_tasks"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT COUNT(*) FROM document WHERE run = '1'")
            out["parsing_documents"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT COUNT(*) FROM document WHERE run = '0'")
            out["unstarted_documents"] = int(cur.fetchone()[0] or 0)

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
                SELECT kb.name, d.name, d.size, d.run, COUNT(*) cnt
                FROM document d
                LEFT JOIN knowledgebase kb ON kb.id = d.kb_id
                GROUP BY kb.name, d.name, d.size, d.run
                """
            )
            groups: dict[tuple[str, str, int], list[tuple[str, int]]] = {}
            for kb_name, name, size, run, cnt in cur.fetchall():
                base = _normalize_document_base_name(name)
                if not base:
                    continue
                key = (kb_name or "", base, int(size or 0))
                groups.setdefault(key, []).append((str(run or ""), int(cnt)))

            dup_groups = 0
            dup_extra = 0
            for entries in groups.values():
                total = sum(n for _, n in entries)
                if total > 1:
                    dup_groups += 1
                    dup_extra += total - 1
            out["duplicate_document_groups"] = dup_groups
            out["duplicate_documents_extra"] = dup_extra

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
        lag_map: dict[str, int] = {}
        for q in _QUEUE_NAMES:
            try:
                groups = client.xinfo_groups(q)
            except Exception:
                lag_map[q] = 0
                continue
            lag = 0
            for g in groups:
                if g.get("name") == _CONSUMER_GROUP:
                    lag = int(g.get("lag") or 0)
                    break
            lag_map[q] = lag
            total_lag += lag
        out["queue_lag"] = total_lag
        out["queue_lag_by_priority"] = lag_map
    except Exception as exc:
        logger.debug("Redis 队列 lag 采集失败: %s", exc)
        if not out.get("error"):
            out["error"] = f"Redis: {exc}"[:200]

    return out
