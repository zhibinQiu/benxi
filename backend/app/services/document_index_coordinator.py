"""文档索引任务协调层：调度、恢复、执行租约。

设计原则（单一真相）：
- **一个 Job 全局至多一个执行者**：PostgreSQL 行锁 + payload 租约（``exec_lease_until``）。
- **一个 Job 只有一条执行链**：同步、解析等待、完成均走 ``run_document_knowledge_index_job``；
  不再单独维护 ``parse_watch`` 任务类型。
- **入队幂等**：同文档/版本已有活跃任务且 ``force=False`` 时复用，不取消重建。
- **调度唯一入口**：``dispatch_document_index_job``（支持 countdown 延迟续跑）。

payload 阶段字段：
- ``index_phase``：``full``（默认，完整同步链）| ``awaiting_parse``（仅轮询 KnowFlow 解析）
- 兼容旧数据：``awaiting_parse: true`` 视为 ``awaiting_parse`` 阶段
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus, JobType

logger = logging.getLogger(__name__)

INDEX_PHASE_FULL = "full"
INDEX_PHASE_AWAITING_PARSE = "awaiting_parse"

_ACTIVE_JOB_STATUSES = (JobStatus.pending.value, JobStatus.running.value)
_EXEC_LEASE_SEC = 7200
_RECOVERY_LOCK_KEY = "platform:recover_document_index_jobs"
_RECOVERY_LOCK_TTL_SEC = 120


def index_phase(payload: dict | None) -> str:
    data = payload or {}
    phase = str(data.get("index_phase") or "").strip()
    if phase in (INDEX_PHASE_FULL, INDEX_PHASE_AWAITING_PARSE):
        return phase
    if data.get("awaiting_parse"):
        return INDEX_PHASE_AWAITING_PARSE
    return INDEX_PHASE_FULL


def is_awaiting_parse_phase(payload: dict | None) -> bool:
    return index_phase(payload) == INDEX_PHASE_AWAITING_PARSE


def parse_watch_started_at(payload: dict | None) -> float | None:
    raw = (payload or {}).get("parse_watch_started_at")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def clear_parse_phase_fields(payload: dict) -> dict:
    out = dict(payload)
    out.pop("awaiting_parse", None)
    out.pop("parse_watch_started_at", None)
    out.pop("index_phase", None)
    out.pop("exec_lease_until", None)
    return out


def enter_awaiting_parse_phase(
    payload: dict,
    *,
    dataset_id: str,
    ragflow_document_id: str,
    mode: str,
    version_id_raw: str | None,
) -> dict:
    out = dict(payload)
    out["index_phase"] = INDEX_PHASE_AWAITING_PARSE
    out["awaiting_parse"] = True
    out["dataset_id"] = dataset_id
    out["ragflow_document_id"] = ragflow_document_id
    out["mode"] = mode
    if version_id_raw:
        out["version_id"] = version_id_raw
    if not out.get("parse_watch_started_at"):
        out["parse_watch_started_at"] = time.time()
    return out


def try_begin_execution(db: Session, job: Job) -> bool:
    """抢占执行租约；失败表示另有 worker 正在执行同一 Job。"""
    locked = db.scalar(select(Job).where(Job.id == job.id).with_for_update())
    if not locked or locked.status not in _ACTIVE_JOB_STATUSES:
        return False

    payload = dict(locked.payload or {})
    now = time.time()
    until = payload.get("exec_lease_until")
    if until is not None:
        try:
            if float(until) > now:
                logger.debug(
                    "文档索引租约未过期，跳过执行 job=%s until=%s",
                    job.id,
                    until,
                )
                return False
        except (TypeError, ValueError):
            pass

    payload["exec_lease_until"] = now + _EXEC_LEASE_SEC
    locked.payload = payload
    db.add(locked)
    db.flush()
    job.payload = locked.payload
    return True


def renew_execution_lease(db: Session, job: Job) -> None:
    locked = db.get(Job, job.id)
    if not locked:
        return
    payload = dict(locked.payload or {})
    payload["exec_lease_until"] = time.time() + _EXEC_LEASE_SEC
    locked.payload = payload
    db.add(locked)
    db.flush()
    job.payload = locked.payload


def end_execution(db: Session, job: Job) -> None:
    locked = db.get(Job, job.id)
    if not locked:
        return
    payload = dict(locked.payload or {})
    payload.pop("exec_lease_until", None)
    locked.payload = payload
    db.add(locked)
    db.flush()
    job.payload = locked.payload


def dispatch(job_id: uuid.UUID, *, countdown: int = 0) -> None:
    """调度文档索引 Job（唯一对外调度入口）。"""
    from app.services.background_job_dispatch import dispatch_document_index_job

    dispatch_document_index_job(job_id, countdown=max(0, int(countdown)))


def ensure_dispatched(job: Job) -> None:
    """活跃 Job 补一次调度（执行端租约会挡重复 worker）。"""
    if job.status not in _ACTIVE_JOB_STATUSES:
        return
    dispatch(job.id)


def _try_acquire_recovery_lock() -> bool:
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        if client is None:
            return True
        return bool(
            client.set(
                _RECOVERY_LOCK_KEY,
                "1",
                nx=True,
                ex=_RECOVERY_LOCK_TTL_SEC,
            )
        )
    except Exception as exc:
        logger.debug("文档索引恢复锁不可用，继续本进程恢复: %s", exc)
        return True


def recover_interrupted_jobs() -> int:
    """进程启动时恢复中断的文档索引任务（全局仅一个进程执行）。"""
    from app.config import get_settings
    from app.database import SessionLocal
    from app.services.job_watchdog_service import is_job_stale
    from app.services.job_service import update_job_status
    from app.services.knowledge_sync_job_service import (
        _index_job_should_abort,
        _index_target_exists,
    )

    if not get_settings().knowflow_enabled:
        return 0
    if not _try_acquire_recovery_lock():
        logger.debug("文档索引恢复已由其他进程执行，跳过")
        return 0

    db = SessionLocal()
    recovered = 0
    cleaned = 0
    try:
        active_jobs = db.scalars(
            select(Job).where(
                Job.type == JobType.document_index.value,
                Job.status.in_(_ACTIVE_JOB_STATUSES),
            )
        ).all()

        for job in active_jobs:
            if is_job_stale(
                job, stale_minutes=int(get_settings().background_job_stale_minutes)
            ):
                continue
            payload = job.payload or {}
            doc_id = job.document_id
            version_id = None
            if payload.get("version_id"):
                try:
                    version_id = uuid.UUID(str(payload["version_id"]))
                except (TypeError, ValueError):
                    version_id = None
            if not _index_target_exists(db, doc_id, version_id):
                continue
            if _index_job_should_abort(db, job):
                continue

            if (
                job.status == JobStatus.running.value
                and not is_awaiting_parse_phase(payload)
            ):
                update_job_status(
                    db,
                    job.id,
                    JobStatus.pending.value,
                    progress=max(0, min(job.progress or 0, 67)),
                )

            dispatch(job.id)
            recovered += 1

        terminal_jobs = db.scalars(
            select(Job).where(
                Job.type == JobType.document_index.value,
                Job.status.in_(
                    (
                        JobStatus.done.value,
                        JobStatus.failed.value,
                        JobStatus.cancelled.value,
                    )
                ),
            )
        ).all()
        for job in terminal_jobs:
            payload = job.payload or {}
            if not payload.get("awaiting_parse") and index_phase(payload) != INDEX_PHASE_AWAITING_PARSE:
                continue
            job.payload = clear_parse_phase_fields(dict(payload))
            db.add(job)
            cleaned += 1

        db.commit()
        if recovered:
            logger.info("已恢复 %s 个文档索引任务", recovered)
        if cleaned:
            logger.info("已清理 %s 个终态文档索引任务的解析阶段标记", cleaned)
    except Exception:
        logger.exception("恢复文档索引任务失败")
        db.rollback()
    finally:
        db.close()
    return recovered
