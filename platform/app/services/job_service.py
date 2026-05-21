from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job, JobEvent, JobStatus, JobType


def create_job(
    db: Session,
    *,
    job_type: str,
    created_by: uuid.UUID,
    document_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> Job:
    job = Job(
        type=job_type,
        status=JobStatus.pending.value,
        created_by=created_by,
        document_id=document_id,
        payload=payload,
    )
    db.add(job)
    db.flush()
    db.add(JobEvent(job_id=job.id, event_type="created", data=payload))
    db.commit()
    db.refresh(job)
    return job


def update_job_status(
    db: Session,
    job_id: uuid.UUID,
    status: str,
    *,
    progress: int | None = None,
    error_message: str | None = None,
) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    job.status = status
    if progress is not None:
        job.progress = progress
    if error_message is not None:
        job.error_message = error_message
    now = datetime.now(timezone.utc)
    if status == JobStatus.running.value and job.started_at is None:
        job.started_at = now
    if status in (JobStatus.done.value, JobStatus.failed.value, JobStatus.cancelled.value):
        job.finished_at = now
    db.add(JobEvent(job_id=job.id, event_type=status, data={"progress": job.progress}))
    db.commit()
    db.refresh(job)
    return job


def list_jobs(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    job_type: str | None = None,
) -> tuple[list[Job], int]:
    base = select(Job).where(Job.created_by == user_id)
    if job_type:
        base = base.where(Job.type == job_type)
    total = db.scalar(select(func.count()).select_from(base)) or 0
    items = db.scalars(
        base.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def enqueue_delete_document(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Job:
    job = create_job(
        db,
        job_type=JobType.delete_document.value,
        created_by=user_id,
        document_id=document_id,
        payload={"document_id": str(document_id)},
    )
    from workers.tasks.maintenance import delete_document_task

    delete_document_task.delay(str(job.id))
    return job
