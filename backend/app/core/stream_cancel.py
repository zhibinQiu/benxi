"""SSE 流协作取消：客户端断开后尽快中断长 await。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar

_cancel_event: ContextVar[asyncio.Event | None] = ContextVar(
    "sse_stream_cancel", default=None
)


def install_stream_cancel() -> asyncio.Event:
    ev = asyncio.Event()
    _cancel_event.set(ev)
    return ev


def clear_stream_cancel() -> None:
    _cancel_event.set(None)


def mark_stream_cancelled() -> None:
    ev = _cancel_event.get()
    if ev is not None:
        ev.set()


def is_stream_cancelled() -> bool:
    ev = _cancel_event.get()
    return bool(ev is not None and ev.is_set())


def raise_if_stream_cancelled() -> None:
    if is_stream_cancelled():
        raise asyncio.CancelledError()


async def await_unless_cancelled(awaitable, *, poll_sec: float = 0.25):
    """等待协程；若 SSE 已取消则取消该任务并抛 CancelledError。"""
    raise_if_stream_cancelled()
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            raise_if_stream_cancelled()
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=poll_sec)
            except asyncio.TimeoutError:
                continue
        return task.result()
    except asyncio.CancelledError:
        task.cancel()
        raise
