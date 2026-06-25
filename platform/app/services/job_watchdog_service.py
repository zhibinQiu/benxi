"""后台任务超时看门狗：pending / running 超过阈值自动取消。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.job import Job, JobStatus
from app.services.job_service import cancel_job

logger = logging.getLogger(__name__)

_CANCELLABLE = (JobStatus.pending.value, JobStatus.running.value)


def stale_job_anchor(job: Job) -> datetime | None:
    """用于判断超时的起始时刻：running 看 started_at，pending 看 created_at。"""
    if job.status == JobStatus.running.value:
        return job.started_at or job.created_at
    if job.status == JobStatus.pending.value:
        return job.created_at
    return None


def is_job_stale(job: Job, *, stale_minutes: int, now: datetime | None = None) -> bool:
    anchor = stale_job_anchor(job)
    if anchor is None:
        return False
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    ts = now or datetime.now(timezone.utc)
    return anchor < ts - timedelta(minutes=max(1, stale_minutes))


def cancel_stale_background_jobs(*, stale_minutes: int | None = None) -> int:
    """取消超时的 pending / running 后台任务。返回取消数量。"""
    settings = get_settings()
    if not settings.background_job_stale_watchdog_enabled:
        return 0

    minutes = max(1, int(stale_minutes or settings.background_job_stale_minutes))
    reason = f"任务运行超过 {minutes} 分钟已自动取消"
    now = datetime.now(timezone.utc)
    cancelled = 0

    db = SessionLocal()
    try:
        jobs = db.scalars(select(Job).where(Job.status.in_(_CANCELLABLE))).all()
        for job in jobs:
            if not is_job_stale(job, stale_minutes=minutes, now=now):
                continue
            try:
                cancel_job(db, job, reason=reason)
                cancelled += 1
                logger.info(
                    "已自动取消超时后台任务 job=%s type=%s status=%s",
                    job.id,
                    job.type,
                    job.status,
                )
            except Exception:
                logger.exception("自动取消超时任务失败 job=%s", job.id)
        if cancelled:
            db.commit()
    except Exception:
        logger.exception("扫描超时后台任务失败")
        db.rollback()
    finally:
        db.close()
    return cancelled


async def _watchdog_loop() -> None:
    await asyncio.sleep(15)
    while True:
        settings = get_settings()
        interval = max(30, int(settings.background_job_stale_watchdog_interval_sec))
        try:
            if settings.background_job_stale_watchdog_enabled:
                await asyncio.to_thread(cancel_stale_background_jobs)
        except Exception:
            logger.exception("后台任务超时看门狗检查失败")
        await asyncio.sleep(interval)


def start_background_job_watchdog() -> asyncio.Task:
    return asyncio.create_task(_watchdog_loop(), name="background-job-watchdog")
