"""Platform-side PDF translation jobs (backed by pdf2zh worker)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.pdf2zh_client import pdf2zh_base_url
from app.models.job import Job, JobStatus, JobType
from app.services.job_service import create_job, update_job_status
from app.services.notification_service import create_notification


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=pdf2zh_base_url(), timeout=httpx.Timeout(60.0))


def pdf2zh_job_id(job: Job) -> str | None:
    if not job.payload:
        return None
    return job.payload.get("pdf2zh_job_id")


def job_to_dict(job: Job) -> dict[str, Any]:
    p = job.payload or {}
    files = p.get("files") or {}
    return {
        "platform_job_id": str(job.id),
        "pdf2zh_job_id": p.get("pdf2zh_job_id"),
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "stage": p.get("stage"),
        "error_message": job.error_message,
        "file_name": p.get("file_name"),
        "lang_in": p.get("lang_in"),
        "lang_out": p.get("lang_out"),
        "service": p.get("service"),
        "files": files,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def get_user_job(db: Session, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
    job = db.get(Job, job_id)
    if not job or job.created_by != user_id:
        return None
    if job.type != JobType.pdf_translate.value:
        return None
    return job


def list_translate_jobs(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
) -> tuple[list[Job], int]:
    base = select(Job).where(
        Job.created_by == user_id,
        Job.type == JobType.pdf_translate.value,
    )
    total = db.scalar(select(func.count()).select_from(base)) or 0
    items = db.scalars(
        base.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def create_translate_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    pdf2zh_job_id_str: str,
    file_name: str,
    lang_in: str,
    lang_out: str,
    service: str,
    document_id: uuid.UUID | None = None,
) -> Job:
    payload: dict[str, Any] = {
        "pdf2zh_job_id": pdf2zh_job_id_str,
        "file_name": file_name,
        "lang_in": lang_in,
        "lang_out": lang_out,
        "service": service,
        "stage": "",
        "files": {},
    }
    if document_id is not None:
        payload["document_id"] = str(document_id)
    job = create_job(
        db,
        job_type=JobType.pdf_translate.value,
        created_by=user_id,
        payload=payload,
    )
    update_job_status(db, job.id, JobStatus.running.value, progress=0)
    from workers.tasks.translate import monitor_translate_job

    monitor_translate_job.delay(str(job.id))
    return job


def sync_job_from_pdf2zh(db: Session, job: Job) -> Job:
    zid = pdf2zh_job_id(job)
    if not zid:
        return job
    try:
        with httpx.Client(base_url=pdf2zh_base_url(), timeout=30.0) as client:
            r = client.get(f"/api/jobs/{zid}")
            r.raise_for_status()
            remote = r.json()
    except Exception as e:
        job.error_message = str(e)
        db.commit()
        return job

    progress = remote.get("progress") or {}
    overall = int(progress.get("overall_progress") or 0)
    stage = progress.get("stage") or ""
    status = remote.get("status") or job.status
    files = remote.get("files") or {}

    payload = dict(job.payload or {})
    payload["stage"] = stage
    payload["files"] = files
    job.payload = payload
    job.progress = overall

    terminal = (
        JobStatus.done.value,
        JobStatus.failed.value,
        JobStatus.cancelled.value,
    )
    if status in terminal and job.status not in terminal:
        update_job_status(
            db,
            job.id,
            status,
            progress=100 if status == JobStatus.done.value else overall,
            error_message=remote.get("error"),
        )
        db.refresh(job)
        if status == JobStatus.done.value:
            title = payload.get("file_name") or "文档"
            create_notification(
                db,
                user_id=job.created_by,
                title="PDF 翻译完成",
                body=f"《{title}》已翻译完成，点击查看结果。",
                link=f"/system/translate?job={job.id}",
            )
    else:
        if status == "running":
            job.status = JobStatus.running.value
        job.progress = overall
        db.commit()
        db.refresh(job)
    return job
