"""后台重任务统一调度：优先 Celery 队列，不可用时回落到有界线程池。

调度策略：
- ``dispatch_*`` 为各 Job 类型的唯一入口；创建 Job 后只调对应 dispatch，不在 service 内
  直接 ``threading.Thread`` 或 ``celery.delay``。
- PageIndex 索引任务强制进程内执行（``job_payload_uses_pageindex``），因建树依赖本机
  工作区与 LLM 配置，远程 Celery Worker 可能版本不一致或缺少 pageindex 包。
"""

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


def _document_index_job_run_inprocess(job_id: uuid.UUID) -> bool:
    """PageIndex 与资讯导入链（DeepDOC→PageIndex）须在本机进程执行。"""
    from app.database import SessionLocal
    from app.models.job import Job
    from app.services.knowledge_parser_service import job_payload_uses_pageindex
    from app.services.knowledge_sync_job_service import SUBSCRIPTION_PIPELINE_MODE

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return False
        payload = job.payload if isinstance(job.payload, dict) else {}
        if job_payload_uses_pageindex(payload):
            return True
        return str(payload.get("mode") or "") == SUBSCRIPTION_PIPELINE_MODE
    finally:
        db.close()


def dispatch_document_index_job(job_id: uuid.UUID) -> None:
    """文档索引 / 重新索引 Job 调度。

    实现思路：读 Job payload → PageIndex 或资讯导入链则跳过 Celery，走 ``submit_background``；
    否则优先 Celery Worker，失败再回落线程池。与 ``knowledge_sync_job_service``
    中 ``run_document_knowledge_index_job`` 配合完成实际索引逻辑。
    """
    run_inprocess = _document_index_job_run_inprocess(job_id)

    if not run_inprocess:
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
    if not _document_index_job_run_inprocess(job_id):
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
