from __future__ import annotations

import time
import uuid

from workers.celery_app import celery_app


@celery_app.task(name="monitor_translate_job")
def monitor_translate_job(platform_job_id: str) -> dict:
    from app.database import SessionLocal
    from app.models.job import Job, JobStatus
    from app.services.job_service import update_job_status
    from app.services.translate_service import sync_job_from_pdf2zh

    db = SessionLocal()
    try:
        job_uuid = uuid.UUID(platform_job_id)
        job = db.get(Job, job_uuid)
        if not job:
            return {"ok": False, "error": "job not found"}

        for _ in range(720):
            db.refresh(job)
            if job.status in (
                JobStatus.done.value,
                JobStatus.failed.value,
                JobStatus.cancelled.value,
            ):
                return {"ok": True, "status": job.status}
            sync_job_from_pdf2zh(db, job)
            db.refresh(job)
            if job.status in (
                JobStatus.done.value,
                JobStatus.failed.value,
                JobStatus.cancelled.value,
            ):
                return {"ok": True, "status": job.status}
            time.sleep(5)

        update_job_status(
            db, job_uuid, JobStatus.failed.value, error_message="监控超时"
        )
        return {"ok": False, "error": "timeout"}
    finally:
        db.close()
