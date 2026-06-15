"""进程内有界后台线程池：Celery 不可用时兜底，避免无界 threading.Thread 耗尽 DB 连接。"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from app.config import get_settings

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

T = TypeVar("T")


def get_background_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            settings = get_settings()
            max_workers = max(1, int(settings.background_job_max_workers))
            _executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="bg-job",
            )
            logger.info("后台任务线程池已启动 max_workers=%s", max_workers)
    return _executor


def submit_background(name: str, fn: Callable[..., T], /, *args, **kwargs) -> None:
    def _wrapped() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("后台任务失败: %s", name)

    get_background_executor().submit(_wrapped)


def shutdown_background_executor(*, wait: bool = False) -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=not wait)
            _executor = None
