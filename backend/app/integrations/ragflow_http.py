"""RAGFlow HTTP 超时与熔断：远程不可达时快速失败，避免占满 DB 连接池。"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cooldown_until: float = 0.0
_consecutive_failures: int = 0


def ragflow_http_timeout() -> float:
    settings = get_settings()
    if settings.ragflow_http_timeout > 0:
        return settings.ragflow_http_timeout
    return 12.0 if settings.remote_deps else 30.0


def should_attempt_ragflow_http() -> bool:
    with _lock:
        ok = time.monotonic() >= _cooldown_until
        if not ok:
            remaining = _cooldown_until - time.monotonic()
            logger.warning(
                "RAGFlow HTTP 熔断中，剩余 %.0fs（连续失败 %d 次），跳过健康检查",
                remaining,
                _consecutive_failures,
            )
        return ok


def mark_ragflow_http_success() -> None:
    global _consecutive_failures, _cooldown_until
    with _lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0


def mark_ragflow_http_failure() -> None:
    global _consecutive_failures, _cooldown_until
    settings = get_settings()
    base = max(settings.ragflow_http_cooldown_sec, 15)
    with _lock:
        _consecutive_failures += 1
        sec = min(base * _consecutive_failures, 120)
        _cooldown_until = time.monotonic() + sec
        logger.warning(
            "RAGFlow HTTP 失败（连续 %d 次），冷却 %.0fs",
            _consecutive_failures,
            sec,
        )


def reset_ragflow_http_circuit_for_tests() -> None:
    global _consecutive_failures, _cooldown_until
    with _lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0


def ragflow_http_client(**kwargs: object) -> httpx.Client:
    timeout = kwargs.pop("timeout", None) or ragflow_http_timeout()
    return httpx.Client(timeout=timeout, **kwargs)
