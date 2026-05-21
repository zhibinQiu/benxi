from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "doc_platform",
    broker=settings.broker,
    backend=settings.result_backend,
    include=["workers.tasks.maintenance", "workers.tasks.translate"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)
