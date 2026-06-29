"""会话 history 与平台/调研路由。"""

from __future__ import annotations

from app.core.session_chat_history import resolve_session_chat_history
from app.database import SessionLocal
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.agent_intent import needs_knowledge_retrieval
from app.services.agent_skill_router import is_platform_operation_message
from app.services.agent_supervisor import _resolve_agent_routes_rule
from sqlalchemy import select


def test_is_platform_operation_message():
    assert is_platform_operation_message("系统中有哪些用户")
    assert is_platform_operation_message("帮我创建一个待办")
    assert is_platform_operation_message("怎么上传文档到知识库")
    assert not is_platform_operation_message("碳排放配额政策是什么")


def test_platform_operation_skips_knowledge_retrieval():
    assert needs_knowledge_retrieval("系统中有哪些用户") is False
    assert needs_knowledge_retrieval("帮我查知识库里的碳报告") is True


def test_route_platform_for_user_list():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        routes = _resolve_agent_routes_rule(db, admin, "系统中有哪些用户")
        assert len(routes) == 1
        assert routes[0].agent_id == "platform"
    finally:
        db.close()


def test_resolve_session_history_uses_server_conversation_only():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        conv = platform_chat_store.get_or_create_conversation(
            db,
            user_id=admin.id,
            scope="ai-home",
            conversation_id=None,
        )
        platform_chat_store.append_turn(
            db,
            conversation=conv,
            user_message="会话A的问题",
            assistant_message="会话A的回答",
        )
        db.commit()
        cid = str(conv.id)

        stale_client = [
            AiChatMessage(role="user", content="其他会话的旧消息"),
            AiChatMessage(role="assistant", content="不应出现在上下文中"),
        ]
        resolved = resolve_session_chat_history(
            db,
            user_id=admin.id,
            scope="ai-home",
            conversation_id=cid,
            client_history=stale_client,
        )
        contents = [m.content for m in resolved]
        assert "会话A的问题" in contents
        assert "其他会话的旧消息" not in contents
    finally:
        db.rollback()
        db.close()
