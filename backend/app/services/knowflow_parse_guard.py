"""KnowFlow 解析提交守卫：入队前检查 RAGFlow task/document 状态，避免重复 parse。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.mysql_conn import get_mysql_connection

logger = logging.getLogger(__name__)

_PARSE_DONE_RUN = frozenset({"3", "DONE", "done"})
_PARSE_RUNNING_RUN = frozenset({"1", "RUNNING", "running"})
_DUP_SUFFIX_RE = re.compile(r"\(\d+\)(\.[^.]+)?$")


def _normalize_document_base_name(name: str | None) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    return _DUP_SUFFIX_RE.sub(lambda m: m.group(1) or "", text).strip()


def _document_parse_incomplete(run: str, progress: float | None) -> bool:
    run_text = (run or "").strip()
    if run_text in _PARSE_DONE_RUN:
        return False
    if progress is not None and progress >= 1:
        return False
    return True


@dataclass(frozen=True)
class KnowflowDocParseState:
    ragflow_document_id: str
    run: str
    progress: float | None
    pending_tasks: int
    running_tasks: int

    @property
    def is_done(self) -> bool:
        run = (self.run or "").strip()
        if run in _PARSE_DONE_RUN:
            return True
        if self.progress is not None and self.progress >= 1:
            return True
        return False

    @property
    def is_parsing(self) -> bool:
        run = (self.run or "").strip()
        return run in _PARSE_RUNNING_RUN or self.running_tasks > 0

    @property
    def has_queued_work(self) -> bool:
        return self.pending_tasks > 0 or self.is_parsing


def _ragflow_mysql_conn(db: Session | None):
    from app.services.model_settings_service import get_ragflow_mysql_settings

    _, password, db_name, host, port = get_ragflow_mysql_settings(db)
    if not password or not host:
        return None
    return get_mysql_connection(
        host=host,
        port=port,
        password=password,
        database=db_name,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )


def fetch_document_parse_state(
    db: Session | None,
    ragflow_document_id: str,
) -> KnowflowDocParseState | None:
    rid = (ragflow_document_id or "").strip()
    if not rid:
        return None
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT run, progress FROM document WHERE id = %s LIMIT 1",
                (rid,),
            )
            row = cur.fetchone()
            if not row:
                return None
            run, progress = row[0], row[1]
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN begin_at IS NULL AND progress >= 0 AND progress < 1 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN begin_at IS NOT NULL AND progress >= 0 AND progress < 1 THEN 1 ELSE 0 END)
                FROM task WHERE doc_id = %s
                """,
                (rid,),
            )
            pending, running = cur.fetchone() or (0, 0)
        prog: float | None
        try:
            prog = float(progress) if progress is not None else None
        except (TypeError, ValueError):
            prog = None
        return KnowflowDocParseState(
            ragflow_document_id=rid,
            run=str(run or ""),
            progress=prog,
            pending_tasks=int(pending or 0),
            running_tasks=int(running or 0),
        )
    except Exception as exc:
        logger.debug("KnowFlow 解析状态查询失败 doc=%s: %s", rid, exc)
        return None
    finally:
        conn.close()


def cancel_document_parse_work(
    db: Session | None,
    ragflow_document_id: str,
) -> dict[str, int]:
    """取消指定文档的待处理/进行中解析任务，并重置 document 状态。"""
    rid = (ragflow_document_id or "").strip()
    if not rid:
        return {"pending_removed": 0, "running_removed": 0, "document_reset": 0}
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return {"pending_removed": 0, "running_removed": 0, "document_reset": 0}
    pending_removed = 0
    running_removed = 0
    document_reset = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM task
                WHERE doc_id = %s AND begin_at IS NULL
                  AND progress >= 0 AND progress < 1
                """,
                (rid,),
            )
            pending_removed = int(cur.rowcount or 0)
            cur.execute(
                """
                DELETE FROM task
                WHERE doc_id = %s AND begin_at IS NOT NULL
                  AND progress >= 0 AND progress < 1
                """,
                (rid,),
            )
            running_removed = int(cur.rowcount or 0)
            cur.execute(
                """
                UPDATE document
                SET run = '0', progress = 0, progress_msg = NULL
                WHERE id = %s AND run IN ('1', '4')
                """,
                (rid,),
            )
            document_reset = int(cur.rowcount or 0)
        conn.commit()
    except Exception as exc:
        logger.warning("KnowFlow 取消文档解析任务失败 doc=%s: %s", rid, exc)
        conn.rollback()
    finally:
        conn.close()
    if pending_removed or running_removed or document_reset:
        logger.info(
            "KnowFlow 已取消文档旧解析任务 doc=%s pending=%s running=%s reset_doc=%s",
            rid,
            pending_removed,
            running_removed,
            document_reset,
        )
    return {
        "pending_removed": pending_removed,
        "running_removed": running_removed,
        "document_reset": document_reset,
    }


def list_incomplete_same_name_document_ids(
    db: Session | None,
    dataset_id: str,
    file_name: str,
    *,
    exclude_ragflow_document_id: str | None = None,
) -> list[str]:
    """同知识库内与 file_name 基名相同、尚未解析完成的 KnowFlow document id。"""
    ds = (dataset_id or "").strip()
    target_base = _normalize_document_base_name(file_name)
    if not ds or not target_base:
        return []
    exclude = (exclude_ragflow_document_id or "").strip()
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return []
    matched: list[str] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, run, progress
                FROM document
                WHERE kb_id = %s AND status = '1'
                """,
                (ds,),
            )
            for rid, name, run, progress in cur.fetchall():
                doc_id = str(rid or "").strip()
                if not doc_id or doc_id == exclude:
                    continue
                if _normalize_document_base_name(str(name or "")) != target_base:
                    continue
                prog: float | None
                try:
                    prog = float(progress) if progress is not None else None
                except (TypeError, ValueError):
                    prog = None
                if _document_parse_incomplete(str(run or ""), prog):
                    matched.append(doc_id)
    except Exception as exc:
        logger.debug(
            "KnowFlow 同名未完成文档查询失败 ds=%s name=%s: %s",
            ds,
            file_name,
            exc,
        )
    finally:
        conn.close()
    return matched


def supersede_incomplete_same_name_documents(
    db: Session | None,
    dataset_id: str,
    file_name: str,
    *,
    exclude_ragflow_document_id: str | None = None,
) -> list[str]:
    """结束同名未完成文档的解析任务，供上传前删除旧副本。"""
    doc_ids = list_incomplete_same_name_document_ids(
        db,
        dataset_id,
        file_name,
        exclude_ragflow_document_id=exclude_ragflow_document_id,
    )
    for doc_id in doc_ids:
        cancel_document_parse_work(db, doc_id)
    if doc_ids:
        logger.info(
            "KnowFlow 同名未完成文档待取代 ds=%s name=%s count=%s",
            dataset_id,
            file_name,
            len(doc_ids),
        )
    return doc_ids


def should_submit_parse(
    db: Session | None,
    ragflow_document_id: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """是否应向 RAGFlow 提交 parse。force=True 仅用于用户显式重新索引。"""
    state = fetch_document_parse_state(db, ragflow_document_id)
    if force:
        if state and state.has_queued_work:
            return True, "cancel_and_submit"
        return True, "force_reindex"
    if state is None:
        return True, "state_unknown"
    if state.is_done:
        return False, "已完成解析"
    if state.has_queued_work:
        return False, "解析任务进行中"
    return True, "submit"


def safe_parse_documents(
    rag,
    dataset_id: str,
    document_ids: list[str],
    *,
    db: Session | None = None,
    force: bool = False,
) -> dict[str, str]:
    """过滤后提交 parse；返回 {doc_id: skip_reason} 被跳过的文档。"""
    from app.integrations.ragflow_client import RagflowError

    ds = (dataset_id or "").strip()
    skipped: dict[str, str] = {}
    to_run: list[str] = []
    for raw in document_ids:
        rid = str(raw or "").strip()
        if not rid:
            continue
        ok, reason = should_submit_parse(db, rid, force=force)
        if not ok:
            skipped[rid] = reason
            logger.info(
                "KnowFlow 跳过重复解析提交 doc=%s reason=%s",
                rid,
                reason,
            )
            continue
        if reason == "cancel_and_submit":
            cancel_document_parse_work(db, rid)
        to_run.append(rid)
    if not to_run:
        return skipped
    try:
        rag.parse_documents(ds, to_run)
    except RagflowError:
        raise
    except Exception as exc:
        raise RagflowError(str(exc)) from exc
    return skipped


def dedupe_pending_tasks(db: Session | None = None) -> dict[str, int]:
    """同 document 仅保留最早一条 pending task，删除其余积压。"""
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return {"removed": 0}
    removed = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, COUNT(*) AS cnt
                FROM task
                WHERE begin_at IS NULL AND progress >= 0 AND progress < 1
                GROUP BY doc_id
                HAVING cnt > 1
                """
            )
            groups = cur.fetchall()
            for doc_id, _cnt in groups:
                cur.execute(
                    """
                    SELECT id FROM task
                    WHERE doc_id = %s AND begin_at IS NULL
                      AND progress >= 0 AND progress < 1
                    ORDER BY id ASC
                    """,
                    (doc_id,),
                )
                ids = [row[0] for row in cur.fetchall()]
                if len(ids) <= 1:
                    continue
                drop = ids[1:]
                placeholders = ",".join(["%s"] * len(drop))
                cur.execute(
                    f"DELETE FROM task WHERE id IN ({placeholders})",
                    drop,
                )
                removed += len(drop)
        conn.commit()
    except Exception as exc:
        logger.warning("KnowFlow pending task 去重失败: %s", exc)
        conn.rollback()
    finally:
        conn.close()
    if removed:
        logger.info("KnowFlow pending task 去重删除 %s 条", removed)
    return {"removed": removed}


def reset_stuck_parsing_documents(db: Session | None = None) -> dict[str, int]:
    """无 running task 但 document.run=解析中 → 重置为未开始，便于 executor 重新消费。"""
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return {"reset": 0}
    reset = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE document d
                SET d.run = '0', d.progress = 0, d.progress_msg = NULL
                WHERE d.run IN ('1', '4')
                  AND NOT EXISTS (
                    SELECT 1 FROM task t
                    WHERE t.doc_id = d.id
                      AND t.begin_at IS NOT NULL
                      AND t.progress >= 0 AND t.progress < 1
                  )
                """
            )
            reset = int(cur.rowcount or 0)
        conn.commit()
    except Exception as exc:
        logger.warning("KnowFlow 卡住文档重置失败: %s", exc)
        conn.rollback()
    finally:
        conn.close()
    if reset:
        logger.info("KnowFlow 重置卡住文档 %s 条", reset)
    return {"reset": reset}


def clear_stuck_queue_tasks(db: Session | None = None) -> dict[str, int]:
    """executor 长时间不消费时，清理 MySQL 中待处理/进行中的解析 task。"""
    conn = _ragflow_mysql_conn(db)
    if conn is None:
        return {"removed": 0}
    removed = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM task
                WHERE progress IS NULL OR (progress >= 0 AND progress < 1)
                """
            )
            removed = int(cur.rowcount or 0)
        conn.commit()
    except Exception as exc:
        logger.warning("KnowFlow 清理积压 task 失败: %s", exc)
        conn.rollback()
    finally:
        conn.close()
    if removed:
        logger.info("KnowFlow 已清理积压 task %s 条", removed)
    return {"removed": removed}


def clear_redis_parse_queues() -> dict[str, int]:
    """清空 Redis 解析队列 stream（配合 MySQL task 清理，便于 executor 重新消费）。"""
    from app.config import get_settings

    settings = get_settings()
    cleared = 0
    try:
        import redis

        redis_timeout = max(0.5, float(settings.redis_socket_timeout_sec))
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=redis_timeout,
            socket_timeout=redis_timeout,
        )
        for q in ("rag_flow_svr_queue", "rag_flow_svr_queue_1"):
            try:
                cleared += int(client.delete(q) or 0)
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Redis 解析队列清理失败: %s", exc)
    if cleared:
        logger.info("KnowFlow 已清空 Redis 解析队列 %s 个", cleared)
    return {"cleared": cleared}


def recover_knowflow_stuck_queue(db: Session | None = None) -> dict[str, Any]:
    """队列恢复：清理积压 task、重置卡住文档、清空 Redis 解析 stream。"""
    cleared = clear_stuck_queue_tasks(db)
    reset = reset_stuck_parsing_documents(db)
    redis = clear_redis_parse_queues()
    return {
        "tasks_cleared": cleared["removed"],
        "documents_reset": reset["reset"],
        "redis_queues_cleared": redis["cleared"],
    }
