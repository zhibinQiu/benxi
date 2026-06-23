"""各对话场景的历史列表与消息加载。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.integrations.agent_chat_client import (
    clear_agent_conversations,
    delete_agent_conversation,
    is_chat_configured,
    list_agent_conversation_messages,
    list_agent_conversations,
)
from app.integrations.dify_chat_client import resolve_dify_credentials
from app.services import platform_chat_store
from app.services.carbon_qa_v2_service import _credentials as carbon_credentials

CHAT_SCOPES = frozenset(
    {"ai-home", "assistant", "carbon-qa", "smart-data-query", "report-generation"}
)

_SCOPE_LABELS = {
    "ai-home": "本析智能",
    "assistant": "本析平台客服",
    "carbon-qa": "双碳问答",
    "smart-data-query": "智能问数",
    "report-generation": "报告生成",
}


def scope_label(scope: str) -> str:
    return _SCOPE_LABELS.get(scope, scope)


def _dify_credentials(scope: str) -> tuple[str, str, str]:
    if scope == "carbon-qa":
        base, key = carbon_credentials()
        return base, key, "双碳问答"
    if scope == "smart-data-query":
        base, key = resolve_dify_credentials()
        return base, key, "智能问数"
    raise bad_request("不支持的对话类型")


async def list_conversations(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    limit: int = 30,
) -> list[dict]:
    if scope not in CHAT_SCOPES:
        raise bad_request("不支持的对话类型")

    if scope in platform_chat_store._VALID_SCOPES:
        return platform_chat_store.list_conversations(
            db, user_id=user_id, scope=scope, limit=limit
        )

    base, key, label = _dify_credentials(scope)
    if not is_chat_configured(base, key):
        return []
    return await list_agent_conversations(
        base_url=base,
        api_key=key,
        user_id=str(user_id),
        limit=limit,
        feature_label=label,
    )


async def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str,
    limit: int = 48,
    before_id: str | None = None,
) -> dict:
    if scope not in CHAT_SCOPES:
        raise bad_request("不支持的对话类型")

    if scope in platform_chat_store._VALID_SCOPES:
        return platform_chat_store.list_messages(
            db,
            user_id=user_id,
            scope=scope,
            conversation_id=conversation_id,
            limit=limit,
            before_id=before_id,
        )

    base, key, label = _dify_credentials(scope)
    if not is_chat_configured(base, key):
        raise not_found("会话不存在")
    rows = await list_agent_conversation_messages(
        base_url=base,
        api_key=key,
        user_id=str(user_id),
        conversation_id=conversation_id,
        limit=limit,
        feature_label=label,
    )
    return {
        "messages": rows,
        "total": len(rows),
        "has_older": False,
        "oldest_id": None,
    }


async def delete_conversation(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str,
) -> None:
    if scope not in CHAT_SCOPES:
        raise bad_request("不支持的对话类型")

    if scope in platform_chat_store._VALID_SCOPES:
        platform_chat_store.delete_conversation(
            db,
            user_id=user_id,
            scope=scope,
            conversation_id=conversation_id,
        )
        db.commit()
        return

    base, key, label = _dify_credentials(scope)
    if not is_chat_configured(base, key):
        raise not_found("会话不存在")
    await delete_agent_conversation(
        base_url=base,
        api_key=key,
        user_id=str(user_id),
        conversation_id=conversation_id,
        feature_label=label,
    )


async def clear_conversations(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
) -> int:
    if scope not in CHAT_SCOPES:
        raise bad_request("不支持的对话类型")

    if scope in platform_chat_store._VALID_SCOPES:
        count = platform_chat_store.clear_conversations(
            db, user_id=user_id, scope=scope
        )
        db.commit()
        return count

    base, key, label = _dify_credentials(scope)
    if not is_chat_configured(base, key):
        return 0
    return await clear_agent_conversations(
        base_url=base,
        api_key=key,
        user_id=str(user_id),
        feature_label=label,
    )
