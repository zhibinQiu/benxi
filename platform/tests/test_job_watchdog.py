"""后台任务超时看门狗。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models.job import Job, JobStatus, JobType
from app.services.job_service import create_job
from app.services.job_watchdog_service import (
    cancel_stale_background_jobs,
    is_job_stale,
    stale_job_anchor,
)


def test_stale_job_anchor_running_prefers_started_at():
    started = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    created = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.running.value,
        created_by=uuid.uuid4(),
        created_at=created,
        started_at=started,
        progress=0,
    )
    assert stale_job_anchor(job) == started


def test_is_job_stale_pending_uses_created_at():
    job = Job(
        id=uuid.uuid4(),
        type=JobType.document_index.value,
        status=JobStatus.pending.value,
        created_by=uuid.uuid4(),
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        progress=0,
    )
    now = datetime(2026, 1, 1, 10, 20, tzinfo=timezone.utc)
    assert is_job_stale(job, stale_minutes=30, now=now) is False
    now = datetime(2026, 1, 1, 10, 31, tzinfo=timezone.utc)
    assert is_job_stale(job, stale_minutes=30, now=now) is True


def test_cancel_stale_background_jobs_cancels_old_running():
    from sqlalchemy import select

    from app.core.phone import bootstrap_login_id
    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        job = create_job(
            db,
            job_type=JobType.maintenance.value,
            created_by=user.id,
        )
        job.status = JobStatus.running.value
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        db.add(job)
        db.commit()

        settings = MagicMock(
            background_job_stale_watchdog_enabled=True,
            background_job_stale_minutes=30,
        )
        with patch(
            "app.services.job_watchdog_service.get_settings", return_value=settings
        ):
            count = cancel_stale_background_jobs()

        assert count == 1
        db.refresh(job)
        assert job.status == JobStatus.cancelled.value
        assert "30 分钟" in (job.error_message or "")
    finally:
        db.close()


def test_cancel_stale_background_jobs_skips_fresh_pending():
    from sqlalchemy import select

    from app.core.phone import bootstrap_login_id
    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        job = create_job(
            db,
            job_type=JobType.document_index.value,
            created_by=user.id,
        )
        settings = MagicMock(
            background_job_stale_watchdog_enabled=True,
            background_job_stale_minutes=30,
        )
        with patch(
            "app.services.job_watchdog_service.get_settings", return_value=settings
        ):
            count = cancel_stale_background_jobs()

        assert count == 0
        db.refresh(job)
        assert job.status == JobStatus.pending.value
    finally:
        db.close()
