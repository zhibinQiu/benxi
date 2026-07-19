"""在 asyncio 事件循环外执行同步 / DB 阻塞任务，避免拖死 API worker。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")

_stream_slot_sem: asyncio.Semaphore | None = None
_db_thread_pool: concurrent.futures.ThreadPoolExecutor | None = None
_db_op_sem: asyncio.Semaphore | None = None


class StreamCapacityError(Exception):
    """本 worker 流式并发已达上限。"""


def _get_pool_size() -> int:
    from app.config import get_settings

    return max(8, int(get_settings().db_pool_size or 15))


def _get_db_thread_pool() -> concurrent.futures.ThreadPoolExecutor:
    """专用 DB 线程池，大小与 DB 连接池稳态容量一致，避免过度排队。"""
    global _db_thread_pool
    if _db_thread_pool is None:
        pool_size = _get_pool_size()
        _db_thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=pool_size,
            thread_name_prefix="db_task",
        )
    return _db_thread_pool


def _get_db_op_semaphore() -> asyncio.Semaphore:
    """限制并发 DB 操作数不超过连接池稳态容量，保护池不被耗尽。"""
    global _db_op_sem
    if _db_op_sem is None:
        _db_op_sem = asyncio.Semaphore(_get_pool_size())
    return _db_op_sem


async def run_sync(func: Callable[..., T], /, *args, **kwargs) -> T:
    """在专用 DB 线程池中执行同步函数。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_db_thread_pool(), func, *args, **kwargs)


async def _run_db_with_slot(fn: Callable[..., T], factory, /) -> T:
    """获取信号量后在线程池中执行 DB 操作。"""
    sem = _get_db_op_semaphore()
    async with sem:
        from app.core.db_circuit import record_db_outcome

        def _run() -> T:
            db = factory()
            try:
                return fn(db)
            finally:
                db.close()

        try:
            result = await run_sync(_run)
            record_db_outcome(None)
            return result
        except Exception as exc:
            record_db_outcome(exc)
            raise


async def run_db_task(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """fn 签名: fn(db: Session, *args, **kwargs) -> T"""

    from app.core.db_circuit import guard_db_circuit
    from app.database import SessionLocal

    guard_db_circuit()

    def _run(db: Session) -> T:
        return fn(db, *args, **kwargs)

    return await _run_db_with_slot(_run, SessionLocal)


async def run_db_read_task(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """只读 run_db_task：优先 DATABASE_READ_URL。"""

    from app.core.db_circuit import guard_db_circuit
    from app.database import read_session_factory

    guard_db_circuit()
    factory = read_session_factory()

    def _run(db: Session) -> T:
        return fn(db, *args, **kwargs)

    return await _run_db_with_slot(_run, factory)


def release_db(db: Session | None) -> None:
    """提交并关闭请求级 Session，长流式 I/O 前归还连接池。"""
    if db is None:
        return
    from app.database import release_db_connection

    try:
        release_db_connection(db)
    finally:
        db.close()


def detach_request_db(db: Session | None) -> None:
    """流式接口在鉴权/校验完成后立刻归还连接（release_db 别名）。"""
    release_db(db)


def resolve_db_user(db: Session, user: uuid.UUID | object) -> object:
    """run_db_task 内用 user_id 重新绑定 Session，避免 detached User。"""
    from app.models.org import User

    if isinstance(user, User):
        try:
            uid = user.id
        except Exception:
            # detached / expired — 从 inspect 或 _sa_instance_state.key 获取
            from sqlalchemy import inspect as sa_inspect

            inst = sa_inspect(user)
            if inst and inst.identity:
                uid = inst.identity[0]
            else:
                # 最后手段：尝试 User 的另一已加载字段或字符串化
                uid = uuid.UUID(str(user))
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
