from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.job import Job, JobEvent, JobStatus, JobType

_CANCELLABLE_STATUSES = (JobStatus.pending.value, JobStatus.running.value)


def create_job(
    db: Session,
    *,
    job_type: str,
    created_by: uuid.UUID,
    document_id: uuid.UUID | None = None,
    payload: dict | None = None,
    commit: bool = True,
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
    if commit:
        db.commit()
        db.refresh(job)
    else:
        db.flush()
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
    if (
        job.status == JobStatus.cancelled.value
        and status != JobStatus.cancelled.value
    ):
        return job
    job.status = status
    if status == JobStatus.done.value:
        job.progress = 100
    elif progress is not None:
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


_FINISHED_STATUSES = (
    JobStatus.done.value,
    JobStatus.failed.value,
    JobStatus.cancelled.value,
)


def _cancel_pdf2zh_remote(pdf2zh_id: str) -> None:
    import httpx

    from app.integrations.pdf2zh_client import pdf2zh_sync_client

    try:
        with pdf2zh_sync_client(timeout_sec=15.0) as client:
            client.delete(f"/api/jobs/{pdf2zh_id}")
    except Exception:
        pass


def cancel_job(db: Session, job: Job) -> Job:
    """终止进行中的任务；翻译任务会同步请求 pdf2zh 取消。"""
    from app.core.exceptions import bad_request

    if job.status not in _CANCELLABLE_STATUSES:
        raise bad_request("仅「等待中」或「运行中」的任务可终止")

    if job.type == JobType.pdf_translate.value:
        from app.services.translate_service import pdf2zh_job_id

        zid = pdf2zh_job_id(job)
        if zid:
            _cancel_pdf2zh_remote(zid)

    if job.type == JobType.document_index.value:
        from app.services.knowledge_sync_job_service import cancel_document_index_job

        return cancel_document_index_job(db, job)

    return update_job_status(
        db,
        job.id,
        JobStatus.cancelled.value,
        error_message="用户已终止",
    )


def clear_jobs(db: Session, user_id: uuid.UUID, *, scope: str) -> int:
    """清理当前用户任务记录。scope: finished=仅已完成/失败/取消；all=除运行中外全部。"""
    stmt = delete(Job).where(Job.created_by == user_id)
    if scope == "finished":
        stmt = stmt.where(Job.status.in_(_FINISHED_STATUSES))
    elif scope == "all":
        stmt = stmt.where(Job.status != JobStatus.running.value)
    else:
        raise ValueError(f"unknown scope: {scope}")
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


def delete_jobs_by_ids(
    db: Session, user_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> int:
    """删除指定任务记录（仅已完成/失败/已取消，且归属当前用户）。"""
    if not job_ids:
        return 0
    stmt = (
        delete(Job)
        .where(Job.created_by == user_id)
        .where(Job.id.in_(job_ids))
        .where(Job.status.in_(_FINISHED_STATUSES))
    )
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


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
