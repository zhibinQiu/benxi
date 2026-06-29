"""在 asyncio 事件循环外执行同步 / DB 阻塞任务，避免拖死 API worker。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")

_stream_slot_sem: asyncio.Semaphore | None = None


class StreamCapacityError(Exception):
    """本 worker 流式并发已达上限。"""


async def run_sync(func: Callable[..., T], /, *args, **kwargs) -> T:
    return await asyncio.to_thread(func, *args, **kwargs)


async def run_db_task(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """fn 签名: fn(db: Session, *args, **kwargs) -> T"""

    from app.core.db_circuit import guard_db_circuit, record_db_outcome
    from app.database import SessionLocal

    guard_db_circuit()

    def _run() -> T:
        db = SessionLocal()
        try:
            return fn(db, *args, **kwargs)
        finally:
            db.close()

    try:
        result = await run_sync(_run)
        record_db_outcome(None)
        return result
    except Exception as exc:
        record_db_outcome(exc)
        raise


async def run_db_read_task(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """只读 run_db_task：优先 DATABASE_READ_URL。"""

    from app.core.db_circuit import guard_db_circuit, record_db_outcome
    from app.database import read_session_factory

    guard_db_circuit()
    factory = read_session_factory()

    def _run() -> T:
        db = factory()
        try:
            return fn(db, *args, **kwargs)
        finally:
            db.close()

    try:
        result = await run_sync(_run)
        record_db_outcome(None)
        return result
    except Exception as exc:
        record_db_outcome(exc)
        raise


def release_db(db: Session | None) -> None:
    """提交并关闭请求级 Session，长流式 I/O 前归还连接池。"""
    if db is None:
        return
    from app.database import release_db_connection

    release_db_connection(db)
    db.close()


def detach_request_db(db: Session | None) -> None:
    """流式接口在鉴权/校验完成后立刻归还连接（release_db 别名）。"""
    release_db(db)


def resolve_db_user(db: Session, user: uuid.UUID | object) -> object:
    """run_db_task 内用 user_id 重新绑定 Session，避免 detached User。"""
    from app.models.org import User

    if isinstance(user, User):
        uid = user.id
    elif isinstance(user, uuid.UUID):
        uid = user
    elif getattr(user, "id", None):
        uid = user.id
    else:
        uid = uuid.UUID(str(user))
    row = db.get(User, uid)
    if row is None:
        raise ValueError("用户不存在")
    return row


def _get_stream_semaphore() -> asyncio.Semaphore:
    global _stream_slot_sem
    if _stream_slot_sem is None:
        from app.config import get_settings

        limit = max(1, int(get_settings().stream_max_concurrent_per_worker or 12))
        _stream_slot_sem = asyncio.Semaphore(limit)
    return _stream_slot_sem


@asynccontextmanager
async def stream_db_slot(*, timeout: float | None = None):
    """限制单 worker 同时进行的长流式任务数，避免连接池与线程被耗尽。"""
    from app.config import get_settings

    if timeout is None:
        timeout = float(get_settings().stream_acquire_timeout or 8.0)
    sem = _get_stream_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise StreamCapacityError("系统繁忙，请稍后重试") from exc
    try:
        yield
    finally:
        sem.release()


async def guard_stream_db(async_iter: AsyncIterator[str]) -> AsyncIterator[str]:
    """包装流式生成器：并发槽 + 确保不依赖请求级 Session。"""
    async with stream_db_slot():
        async for item in async_iter:
            yield item
