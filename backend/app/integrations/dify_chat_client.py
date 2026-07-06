"""兼容旧导入 — 智能问数 v2 对话客户端。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.config import get_settings
from app.core.exceptions import bad_request
from app.integrations.agent_chat_client import (
    agent_chat_blocking,
    is_chat_configured,
    iter_agent_chat_stream,
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


def resolve_dify_credentials() -> tuple[str, str]:
    settings = get_settings()
    base = (_clean(settings.smart_data_query_v2_dify_base_url) or "").rstrip("/")
    key = _clean(settings.smart_data_query_v2_dify_api_key)
    if not base or not key:
        raise bad_request("智能问数 v2 未配置，请联系管理员设置对话 API")
    return base, key


def is_dify_configured() -> bool:
    settings = get_settings()
    return is_chat_configured(
        settings.smart_data_query_v2_dify_base_url,
        settings.smart_data_query_v2_dify_api_key,
    )


async def dify_chat_blocking(
    *,
    query: str,
    user_id: str,
    conversation_id: str | None = None,
) -> dict:
    base, key = resolve_dify_credentials()
    return await agent_chat_blocking(
        base_url=base,
        api_key=key,
        query=query,
        user_id=user_id,
        conversation_id=conversation_id,
        feature_label="智能问数",
        model_name="smart-data-query-v2",
    )


async def iter_dify_chat_stream(
    *,
    query: str,
    user_id: str,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    base, key = resolve_dify_credentials()
    async for chunk in iter_agent_chat_stream(
        base_url=base,
        api_key=key,
        query=query,
        user_id=user_id,
        conversation_id=conversation_id,
        feature_label="智能问数",
        model_name="smart-data-query-v2",
    ):
        yield chunk
