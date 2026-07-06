"""平台侧对话存储。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import not_found
from app.models.platform_chat import PlatformChatConversation, PlatformChatMessage

_VALID_SCOPES = frozenset({"ai-home", "digital-robot", "assistant", "report-generation"})


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

    now = datetime.now(timezone.utc)
    db.add(
        PlatformChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message,
            created_at=now,
        )
    )
    if assistant_message:
        db.add(
            PlatformChatMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
                created_at=now + timedelta(microseconds=1),
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


def _role_rank_column():
    """同秒内 user 须排在 assistant 之前（UUID 主键无序）。"""
    return case(
        (PlatformChatMessage.role == "user", 0),
        (PlatformChatMessage.role == "assistant", 1),
        else_=2,
    )


def _role_rank_value(role: str) -> int:
    if role == "user":
        return 0
    if role == "assistant":
        return 1
    return 2


def _message_desc_order():
    role_rank = _role_rank_column()
    return (
        PlatformChatMessage.created_at.desc(),
        role_rank.desc(),
        PlatformChatMessage.id.desc(),
    )


def _is_older_than_message(first: PlatformChatMessage):
    """严格早于 first 在对话时间线上的位置（用于分页与 has_older）。"""
    role_rank = _role_rank_column()
    first_rank = _role_rank_value(first.role)
    return or_(
        PlatformChatMessage.created_at < first.created_at,
        and_(
            PlatformChatMessage.created_at == first.created_at,
            or_(
                role_rank < first_rank,
                and_(
                    role_rank == first_rank,
                    PlatformChatMessage.id < first.id,
                ),
            ),
        ),
    )


def _is_before_cursor(before_row: PlatformChatMessage):
    """分页游标：返回严格早于 before_row 的消息。"""
    return _is_older_than_message(before_row)


def _message_row_dict(row: PlatformChatMessage) -> dict:
    return {
        "id": str(row.id),
        "role": row.role,
        "content": row.content,
    }


def _has_older_messages(db: Session, *, conversation_id: uuid.UUID, first: PlatformChatMessage) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(PlatformChatMessage)
        .where(
            PlatformChatMessage.conversation_id == conversation_id,
            _is_older_than_message(first),
        )
    )
    return bool(count)


def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str,
    limit: int = 48,
    before_id: str | None = None,
) -> dict:
    try:
        cid = uuid.UUID(str(conversation_id))
    except ValueError as e:
        raise not_found("会话不存在") from e

    conv = db.get(PlatformChatConversation, cid)
    if not conv or conv.user_id != user_id or conv.scope != scope:
        raise not_found("会话不存在")

    page_limit = max(1, min(limit, 100))
    total = (
        db.scalar(
            select(func.count())
            .select_from(PlatformChatMessage)
            .where(PlatformChatMessage.conversation_id == conv.id)
        )
        or 0
    )

    if before_id:
        try:
            bid = uuid.UUID(str(before_id))
        except ValueError as e:
            raise not_found("消息不存在") from e
        before_row = db.get(PlatformChatMessage, bid)
        if not before_row or before_row.conversation_id != conv.id:
            raise not_found("消息不存在")
        stmt = (
            select(PlatformChatMessage)
            .where(
                PlatformChatMessage.conversation_id == conv.id,
                _is_before_cursor(before_row),
            )
            .order_by(*_message_desc_order())
            .limit(page_limit)
        )
        rows = list(reversed(db.scalars(stmt).all()))
    else:
        stmt = (
            select(PlatformChatMessage)
            .where(PlatformChatMessage.conversation_id == conv.id)
            .order_by(*_message_desc_order())
            .limit(page_limit)
        )
        rows = list(reversed(db.scalars(stmt).all()))

    has_older = _has_older_messages(db, conversation_id=conv.id, first=rows[0]) if rows else False
    return {
        "messages": [_message_row_dict(row) for row in rows],
        "total": int(total),
        "has_older": has_older,
        "oldest_id": str(rows[0].id) if rows else None,
    }


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
