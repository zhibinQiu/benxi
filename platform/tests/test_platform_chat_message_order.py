"""平台对话消息顺序 — 同秒问答不得颠倒。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.org import User
from app.models.platform_chat import PlatformChatConversation, PlatformChatMessage
from app.services import platform_chat_store


def test_list_messages_user_before_assistant_when_same_timestamp():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None

        conv = PlatformChatConversation(user_id=user.id, scope="ai-home", title="顺序测试")
        db.add(conv)
        db.flush()

        ts = datetime(2026, 6, 23, 9, 0, 0, tzinfo=timezone.utc)
        # 故意让 assistant UUID 字典序小于 user，旧逻辑会排反
        user_id_msg = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        assistant_id_msg = uuid.UUID("00000000-0000-0000-0000-000000000001")

        db.add(
            PlatformChatMessage(
                id=user_id_msg,
                conversation_id=conv.id,
                role="user",
                content="问题 xxx",
                created_at=ts,
            )
        )
        db.add(
            PlatformChatMessage(
                id=assistant_id_msg,
                conversation_id=conv.id,
                role="assistant",
                content="回答 yyyy",
                created_at=ts,
            )
        )
        db.commit()

        payload = platform_chat_store.list_messages(
            db,
            user_id=user.id,
            scope="ai-home",
            conversation_id=str(conv.id),
            limit=10,
        )
        roles = [m["role"] for m in payload["messages"]]
        contents = [m["content"] for m in payload["messages"]]
        assert roles == ["user", "assistant"]
        assert contents == ["问题 xxx", "回答 yyyy"]
    finally:
        db.rollback()
        db.close()


def test_append_turn_assigns_monotonic_timestamps():
    db = SessionLocal()
    try:
        from sqlalchemy import select

        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None

        conv = platform_chat_store.get_or_create_conversation(
            db, user_id=user.id, scope="ai-home", conversation_id=None
        )
        platform_chat_store.append_turn(
            db,
            conversation=conv,
            user_message="你好",
            assistant_message="您好",
        )
        db.commit()

        rows = list(
            db.scalars(
                select(PlatformChatMessage)
                .where(PlatformChatMessage.conversation_id == conv.id)
                .order_by(PlatformChatMessage.created_at.asc())
            ).all()
        )
        assert len(rows) == 2
        assert rows[0].role == "user"
        assert rows[1].role == "assistant"
        assert rows[1].created_at >= rows[0].created_at
    finally:
        db.rollback()
        db.close()
