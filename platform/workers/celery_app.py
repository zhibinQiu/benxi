import logging

from celery import Celery
from celery.signals import worker_ready

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "doc_platform",
    broker=settings.broker,
    backend=settings.result_backend,
    include=[
        "workers.tasks.maintenance",
        "workers.tasks.translate",
        "workers.tasks.platform_jobs",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # 定期回收 worker 子进程，降低长任务内存泄漏风险
    worker_max_tasks_per_child=25,
    task_soft_time_limit=3600,
    task_time_limit=3900,
)


@worker_ready.connect
def _recover_document_index_jobs_on_worker_start(**_kwargs) -> None:
    """Worker 重启后恢复中断的文档索引任务（与 API 启动恢复互补）。"""
    try:
        from app.services.knowledge_sync_job_service import (
            recover_interrupted_document_index_jobs,
        )

        recovered = recover_interrupted_document_index_jobs()
        if recovered:
            logger.info("Worker 启动已恢复 %s 个文档索引/解析续跑任务", recovered)
    except Exception:
        logger.exception("Worker 启动恢复文档索引任务失败")
