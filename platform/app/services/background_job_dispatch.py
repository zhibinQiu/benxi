"""后台重任务统一调度：优先 Celery 队列，不可用时回落到有界线程池。"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable

from app.config import get_settings
from app.core.background_executor import submit_background

logger = logging.getLogger(__name__)


def _try_celery(task_fn, args: list, *, countdown: int, label: str) -> bool:
    settings = get_settings()
    if not settings.background_jobs_use_celery:
        return False
    try:
        if countdown > 0:
            task_fn.apply_async(args=args, countdown=countdown)
        else:
            task_fn.delay(*args)
        return True
    except Exception as exc:
        logger.warning(
            "Celery 调度失败 (%s)，回落进程内线程池: %s",
            label,
            exc,
        )
        return False


def submit_light_background(name: str, fn: Callable, /, *args, **kwargs) -> None:
    """登录预热等轻量任务：仅走有界线程池，不占 Celery worker。"""
    submit_background(name, fn, *args, **kwargs)


def dispatch_document_index_job(job_id: uuid.UUID) -> None:
    from workers.tasks.platform_jobs import run_document_index_job_task

    if _try_celery(
        run_document_index_job_task,
        [str(job_id)],
        countdown=0,
        label=f"document-index-{job_id}",
    ):
        return
    from app.services.knowledge_sync_job_service import run_document_knowledge_index_job

    submit_background(
        f"document-index-{job_id}",
        run_document_knowledge_index_job,
        job_id,
    )


def dispatch_subscription_import_job(job_id: uuid.UUID) -> None:
    from workers.tasks.platform_jobs import run_subscription_import_job_task

    if _try_celery(
        run_subscription_import_job_task,
        [str(job_id)],
        countdown=0,
        label=f"subscription-import-{job_id}",
    ):
        return
    from app.services.subscription_import_service import run_subscription_import_job

    submit_background(
        f"subscription-import-{job_id}",
        run_subscription_import_job,
        job_id,
    )


def dispatch_post_upload_processing(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from workers.tasks.platform_jobs import run_post_upload_job_task

    args = [str(document_id), str(version_id), str(user_id)]
    if _try_celery(
        run_post_upload_job_task,
        args,
        countdown=0,
        label=f"post-upload-{version_id}",
    ):
        return
    from app.services.documents.post_upload import run_post_upload_processing

    submit_background(
        f"post-upload-{version_id}",
        run_post_upload_processing,
        document_id,
        version_id,
        user_id,
    )


def dispatch_parse_watch(job_id: uuid.UUID, *, countdown: int = 0) -> None:
    from workers.tasks.platform_jobs import run_parse_watch_task

    if _try_celery(
        run_parse_watch_task,
        [str(job_id)],
        countdown=countdown,
        label=f"parse-watch-{job_id}",
    ):
        return
    if countdown > 0:
        threading.Timer(
            countdown,
            lambda: _dispatch_parse_watch_inprocess(job_id),
        ).start()
        return
    _dispatch_parse_watch_inprocess(job_id)


def _dispatch_parse_watch_inprocess(job_id: uuid.UUID) -> None:
    from app.services.knowledge_sync_job_service import _run_parse_watch

    submit_background(f"parse-watch-{job_id}", _run_parse_watch, job_id)
