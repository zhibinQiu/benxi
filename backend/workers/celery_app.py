from celery import Celery

from app.config import get_settings

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
