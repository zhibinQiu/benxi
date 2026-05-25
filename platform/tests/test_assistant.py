"""智能客服知识库与 API。"""

from __future__ import annotations

from app.services.assistant_knowledge import build_platform_knowledge
from sqlalchemy import select

from app.database import SessionLocal
from app.models.org import User


def test_build_platform_knowledge_contains_nav():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        text = build_platform_knowledge(db, admin, page_hint="文档库")
        assert "文档库" in text
        assert "任务中心" in text
        assert "系统功能" in text
    finally:
        db.close()


def test_assistant_chat_requires_auth(client):
    r = client.post(
        "/api/v1/assistant/chat",
        json={"message": "你好"},
    )
    assert r.status_code == 401
