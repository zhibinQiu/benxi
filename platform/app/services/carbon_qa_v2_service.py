"""双碳问答 v2 — 对话服务。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.config import get_settings
from app.integrations.agent_chat_client import (
    agent_chat_blocking,
    is_chat_configured,
    iter_agent_chat_stream,
)


def _credentials() -> tuple[str, str]:
    s = get_settings()
    return (
        (s.carbon_qa_v2_chat_base_url or "").strip(),
        (s.carbon_qa_v2_chat_api_key or "").strip(),
    )


async def chat_carbon_qa_v2(
    *,
    message: str,
    user_id: str,
    conversation_id: str | None = None,
) -> dict:
    base, key = _credentials()
    return await agent_chat_blocking(
        base_url=base,
        api_key=key,
        query=message,
        user_id=user_id,
        conversation_id=conversation_id,
        feature_label="双碳问答",
        model_name="carbon-qa-v2",
    )


async def iter_carbon_qa_v2_stream(
    *,
    message: str,
    user_id: str,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    base, key = _credentials()
    async for chunk in iter_agent_chat_stream(
        base_url=base,
        api_key=key,
        query=message,
        user_id=user_id,
        conversation_id=conversation_id,
        feature_label="双碳问答",
        model_name="carbon-qa-v2",
    ):
        yield chunk


def meta() -> dict:
    base, key = _credentials()
    return {
        "available": is_chat_configured(base, key),
        "provider": "carbon_qa_v2",
    }
