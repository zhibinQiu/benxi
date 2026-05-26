"""智能问数 v2 — 问数对话服务。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.integrations.dify_chat_client import (
    dify_chat_blocking,
    is_dify_configured,
    iter_dify_chat_stream,
)


async def chat_smart_data_query_v2(
    *,
    message: str,
    user_id: str,
    conversation_id: str | None = None,
) -> dict:
    return await dify_chat_blocking(
        query=message,
        user_id=user_id,
        conversation_id=conversation_id,
    )


async def iter_smart_data_query_v2_stream(
    *,
    message: str,
    user_id: str,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    async for chunk in iter_dify_chat_stream(
        query=message,
        user_id=user_id,
        conversation_id=conversation_id,
    ):
        yield chunk


def meta() -> dict:
    return {
        "available": is_dify_configured(),
        "provider": "smart_data_query_v2",
    }
