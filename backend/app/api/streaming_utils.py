"""流式 API 共用：归还请求级 DB 连接 + 并发背压。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.async_db import StreamCapacityError, detach_request_db, stream_db_slot
from app.core.user_messages import KNOWLEDGE_SERVICE_UNAVAILABLE, sanitize_user_message

logger = logging.getLogger(__name__)


def _dumps(obj: dict) -> str:
    """SSE 流输出使用 orjson 加速序列化。"""
    import orjson

    return orjson.dumps(obj).decode("utf-8")


async def stream_sse_payloads(
    db: Session | None,
    payload_iter: Callable[[], AsyncIterator[str]],
) -> AsyncIterator[str]:
    """鉴权完成后释放 get_db，并在并发槽内产出 SSE data 行。"""
    detach_request_db(db)
    try:
        async with stream_db_slot():
            async for payload in payload_iter():
                yield f"data: {payload}\n\n"
    except StreamCapacityError as exc:
        yield f"data: {_dumps({'error': str(exc)})}\n\n"
    except Exception as exc:
        logger.exception("stream_sse_payloads failed")
        message = sanitize_user_message(
            str(exc),
            fallback=KNOWLEDGE_SERVICE_UNAVAILABLE,
        )
        yield f"data: {_dumps({'error': message})}\n\n"


_POLL_EVENT_TERMINAL = frozenset({"done", "failed", "cancelled"})


async def poll_and_stream(
    db_factory: Callable[[], Session],
    fetch_payload: Callable[[Session], dict[str, Any] | None],
    *,
    terminal_statuses: frozenset[str] = _POLL_EVENT_TERMINAL,
    max_polls: int = 600,
    interval: float = 1.0,
) -> AsyncIterator[dict[str, Any]]:
    """通用 SSE 轮询生成器。

    不断轮询后台任务的状态，通过 SSE event 流式输出。适用于 Job / CompareJob 等场景。

    *db_factory* — 返回新 Session 的可调用（如 ``SessionLocal``）。
    *fetch_payload* — 接收 Session，返回序列化的状态 dict；若返回 None 表示任务已不存在。
    """
    last_status = None
    for _ in range(max_polls):
        poll_db = db_factory()
        try:
            payload = fetch_payload(poll_db)
            if payload is None:
                break
        finally:
            poll_db.close()
        status = payload.get("status")
        if status != last_status:
            last_status = status
            yield {"event": "status", "data": json.dumps(payload, default=str)}
        if status in terminal_statuses:
            yield {"event": "complete", "data": json.dumps(payload, default=str)}
            break
        await asyncio.sleep(interval)
    else:
        yield {
            "event": "timeout",
            "data": json.dumps({"message": "poll timeout"}, default=str),
        }
