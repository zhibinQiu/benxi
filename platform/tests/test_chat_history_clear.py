"""历史对话清除 API。"""

from __future__ import annotations

import uuid

from app.database import SessionLocal
from app.models.platform_chat import PlatformChatConversation, PlatformChatMessage
from app.services import platform_chat_store


def _seed_conversation(user_id: uuid.UUID, *, scope: str = "ai-home") -> uuid.UUID:
    db = SessionLocal()
    try:
        conv = PlatformChatConversation(user_id=user_id, scope=scope, title="测试对话")
        db.add(conv)
        db.flush()
        db.add(
            PlatformChatMessage(
                conversation_id=conv.id,
                role="user",
                content="你好",
            )
        )
        db.commit()
        return conv.id
    finally:
        db.close()


def test_delete_chat_conversation(client, admin_token):
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        cid = _seed_conversation(user.id)
    finally:
        db.close()

    r = client.delete(
        f"/api/v1/chat-history/ai-home/conversations/{cid}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["ok"] is True

    db = SessionLocal()
    try:
        assert db.get(PlatformChatConversation, cid) is None
    finally:
        db.close()


def test_clear_chat_conversations(client, admin_token):
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        user_id = user.id
        _seed_conversation(user_id)
        _seed_conversation(user_id, scope="assistant")
    finally:
        db.close()

    r = client.delete(
        "/api/v1/chat-history/ai-home/conversations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["ok"] is True
    assert body["deleted"] >= 1

    db = SessionLocal()
    try:
        rows = platform_chat_store.list_conversations(
            db, user_id=user_id, scope="ai-home", limit=50
        )
        assert rows == []
        assistant_rows = platform_chat_store.list_conversations(
            db, user_id=user_id, scope="assistant", limit=50
        )
        assert len(assistant_rows) >= 1
    finally:
        db.close()
