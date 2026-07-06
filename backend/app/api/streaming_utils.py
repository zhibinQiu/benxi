"""流式 API 共用：归还请求级 DB 连接 + 并发背压。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

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
