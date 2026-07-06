from __future__ import annotations

import uuid

from workers.celery_app import celery_app


@celery_app.task(name="delete_document")
def delete_document_task(job_id: str) -> dict:
    from app.database import SessionLocal
    from app.models.document import Document, DocumentPermission, DocumentVersion
    from app.models.job import JobStatus
    from app.services.job_service import update_job_status
    from app.services.notification_service import create_notification
    from app.storage.object_store import get_object_store

    db = SessionLocal()
    try:
        job_uuid = uuid.UUID(job_id)
        from app.models.job import Job

        job = db.get(Job, job_uuid)
        if not job or not job.document_id:
            update_job_status(db, job_uuid, JobStatus.failed.value, error_message="Invalid job")
            return {"ok": False}

        update_job_status(db, job_uuid, JobStatus.running.value, progress=10)
        document_id = job.document_id
        prefix = f"docs/{document_id}/"
        get_object_store().delete_prefix(prefix)

        update_job_status(db, job_uuid, JobStatus.running.value, progress=60)
        db.query(DocumentPermission).filter(
            DocumentPermission.document_id == document_id
        ).delete()
        db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id
        ).delete()

        update_job_status(db, job_uuid, JobStatus.running.value, progress=90)
        doc = db.get(Document, document_id)
        if doc:
            db.delete(doc)

        update_job_status(db, job_uuid, JobStatus.done.value, progress=100)
        create_notification(
            db,
            user_id=job.created_by,
            title="文档已删除",
            body=f"文档 {document_id} 及关联文件已清理完成。",
            link=None,
        )
        db.commit()
        return {"ok": True, "document_id": str(document_id)}
    except Exception as e:
        db.rollback()
        try:
            update_job_status(
                db, uuid.UUID(job_id), JobStatus.failed.value, error_message=str(e)
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
