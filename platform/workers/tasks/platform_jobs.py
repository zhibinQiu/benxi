"""平台重后台任务（文档索引、导入、上传后处理）— 由 Celery Worker 串行/限并发执行。"""

from __future__ import annotations

import uuid

from workers.celery_app import celery_app


@celery_app.task(
    name="platform.run_document_index_job",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_document_index_job_task(self, job_id: str) -> dict:
    from app.services.knowledge_sync_job_service import run_document_knowledge_index_job

    run_document_knowledge_index_job(uuid.UUID(job_id))
    return {"ok": True, "job_id": job_id}


@celery_app.task(
    name="platform.run_subscription_import_job",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_subscription_import_job_task(self, job_id: str) -> dict:
    from app.services.subscription_import_service import run_subscription_import_job

    run_subscription_import_job(uuid.UUID(job_id))
    return {"ok": True, "job_id": job_id}


@celery_app.task(
    name="platform.run_post_upload_job",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_post_upload_job_task(
    self,
    document_id: str,
    version_id: str,
    user_id: str,
) -> dict:
    from app.services.documents.post_upload import run_post_upload_processing

    run_post_upload_processing(
        uuid.UUID(document_id),
        uuid.UUID(version_id),
        uuid.UUID(user_id),
    )
    return {"ok": True, "version_id": version_id}


@celery_app.task(
    name="platform.run_parse_watch",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_parse_watch_task(self, job_id: str) -> dict:
    from app.services.knowledge_sync_job_service import _run_parse_watch

    _run_parse_watch(uuid.UUID(job_id))
    return {"ok": True, "job_id": job_id}
