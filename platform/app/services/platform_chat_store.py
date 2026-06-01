"""平台侧对话存储。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import not_found
from app.models.platform_chat import PlatformChatConversation, PlatformChatMessage

_VALID_SCOPES = frozenset({"ai-home", "assistant"})


def _title_from_message(text: str, *, limit: int = 48) -> str:
    one_line = " ".join(text.strip().split())
    if not one_line:
        return "新对话"
    return one_line if len(one_line) <= limit else f"{one_line[: limit - 1]}…"


def get_or_create_conversation(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str | None,
) -> PlatformChatConversation:
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unsupported platform chat scope: {scope}")

    if conversation_id:
        try:
            cid = uuid.UUID(str(conversation_id))
        except ValueError as e:
            raise not_found("会话不存在") from e
        row = db.get(PlatformChatConversation, cid)
        if not row or row.user_id != user_id or row.scope != scope:
            raise not_found("会话不存在")
        return row

    row = PlatformChatConversation(
        user_id=user_id,
        scope=scope,
        title="新对话",
    )
    db.add(row)
    db.flush()
    return row


def append_turn(
    db: Session,
    *,
    conversation: PlatformChatConversation,
    user_message: str,
    assistant_message: str,
) -> None:
    user_message = user_message.strip()
    assistant_message = assistant_message.strip()
    if not user_message:
        return

    if conversation.title == "新对话":
        conversation.title = _title_from_message(user_message)

    db.add(
        PlatformChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message,
        )
    )
    if assistant_message:
        db.add(
            PlatformChatMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
            )
        )
    conversation.updated_at = datetime.now(timezone.utc)
    db.flush()


def list_conversations(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    limit: int = 30,
) -> list[dict]:
    if scope not in _VALID_SCOPES:
        return []

    stmt = (
        select(PlatformChatConversation)
        .where(
            PlatformChatConversation.user_id == user_id,
            PlatformChatConversation.scope == scope,
        )
        .order_by(PlatformChatConversation.updated_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = db.scalars(stmt).all()
    return [
        {
            "id": str(row.id),
            "title": row.title,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str,
) -> list[dict]:
    try:
        cid = uuid.UUID(str(conversation_id))
    except ValueError as e:
        raise not_found("会话不存在") from e

    conv = db.get(PlatformChatConversation, cid)
    if not conv or conv.user_id != user_id or conv.scope != scope:
        raise not_found("会话不存在")

    stmt = (
        select(PlatformChatMessage)
        .where(PlatformChatMessage.conversation_id == conv.id)
        .order_by(PlatformChatMessage.created_at.asc())
    )
    rows = db.scalars(stmt).all()
    return [{"role": row.role, "content": row.content} for row in rows]


def delete_conversation(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str,
) -> None:
    if scope not in _VALID_SCOPES:
        raise not_found("会话不存在")
    try:
        cid = uuid.UUID(str(conversation_id))
    except ValueError as e:
        raise not_found("会话不存在") from e

    conv = db.get(PlatformChatConversation, cid)
    if not conv or conv.user_id != user_id or conv.scope != scope:
        raise not_found("会话不存在")
    db.delete(conv)
    db.flush()


def clear_conversations(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
) -> int:
    if scope not in _VALID_SCOPES:
        return 0

    stmt = select(PlatformChatConversation).where(
        PlatformChatConversation.user_id == user_id,
        PlatformChatConversation.scope == scope,
    )
    rows = list(db.scalars(stmt).all())
    for row in rows:
        db.delete(row)
    if rows:
        db.flush()
    return len(rows)
