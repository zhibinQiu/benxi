"""数据库访问统一熔断：连接池排队超时、连续连接/执行失败时快速失败。"""

from __future__ import annotations

import threading
import time

from app.config import get_settings

_lock = threading.Lock()
_cooldown_until: float = 0.0
_consecutive_failures: int = 0

DB_CIRCUIT_MESSAGE = "系统繁忙，请稍后重试"


class DbCircuitOpenError(Exception):
    """熔断打开，拒绝新的数据库访问。"""


def db_circuit_enabled() -> bool:
    return bool(get_settings().db_circuit_enabled)


def should_attempt_db() -> bool:
    if not db_circuit_enabled():
        return True
    with _lock:
        return time.monotonic() >= _cooldown_until


def guard_db_circuit() -> None:
    """在获取连接前检查熔断状态。"""
    if not should_attempt_db():
        raise DbCircuitOpenError(DB_CIRCUIT_MESSAGE)


def mark_db_success() -> None:
    global _consecutive_failures, _cooldown_until
    if not db_circuit_enabled():
        return
    with _lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0


def mark_db_failure() -> None:
    global _consecutive_failures, _cooldown_until
    if not db_circuit_enabled():
        return
    settings = get_settings()
    threshold = max(1, int(settings.db_circuit_failure_threshold or 5))
    base = max(int(settings.db_circuit_cooldown_sec or 20), 5)
    with _lock:
        _consecutive_failures += 1
        if _consecutive_failures >= threshold:
            sec = min(base * (_consecutive_failures - threshold + 1), 120)
            _cooldown_until = time.monotonic() + sec


def is_db_failure(exc: BaseException) -> bool:
    """判断是否属于应触发熔断的数据库异常。"""
    if exc is None:
        return False
    try:
        from sqlalchemy.exc import DBAPIError, OperationalError
        from sqlalchemy.exc import TimeoutError as SATimeoutError
    except ImportError:
        return False

    if isinstance(exc, SATimeoutError):
        return True
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True
    msg = str(exc).lower()
    if "queuepool limit" in msg or "connection timed out" in msg:
        return True
    if "could not connect" in msg or "server closed the connection" in msg:
        return True
    return False


def record_db_outcome(exc: BaseException | None) -> None:
    if exc is None:
        mark_db_success()
    elif is_db_failure(exc):
        mark_db_failure()


def reset_db_circuit_for_tests() -> None:
    global _consecutive_failures, _cooldown_until
    with _lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0
