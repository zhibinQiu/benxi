"""专精智能体路由目录与上下文匹配测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import should_orchestrator_reply_directly
from app.services.agent_routing_catalog import (
    build_supervisor_routing_catalog,
    message_targets_uploaded_skill,
)
from app.services.agent_supervisor import resolve_agent_route


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_should_orchestrator_direct_for_hello_and_simple():
    assert should_orchestrator_reply_directly("你好") is True
    assert should_orchestrator_reply_directly("什么是光合作用") is True
    assert should_orchestrator_reply_directly("帮我检索知识库里的碳报告") is False


def test_build_supervisor_routing_catalog_includes_descriptions():
    db = SessionLocal()
    try:
        text = build_supervisor_routing_catalog(db, agent_ids={"skill-dev", "platform"})
        assert "skill-dev" in text
        assert "platform" in text
        assert "Use when" in text
    finally:
        db.close()


def test_route_beijing_followup_to_skill_dev_with_history():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        history = [
            AiChatMessage(
                role="user",
                content="生成一个 skill 爬取碳市场价格",
            ),
            AiChatMessage(
                role="assistant",
                content="已创建 carbon-market-price，可直接问北京碳价。",
            ),
        ]
        assert message_targets_uploaded_skill(db, user, "北京", history)
        route = resolve_agent_route(db, user, "北京", chat_history=history)
        assert route.agent_id == "skill-dev"
    finally:
        db.close()


def test_unrelated_question_after_skill_history_routes_orchestrator():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        history = [
            AiChatMessage(
                role="user",
                content="生成一个 skill 爬取碳市场价格",
            ),
            AiChatMessage(
                role="assistant",
                content="已创建 carbon-market-price，可直接问北京碳价。",
            ),
        ]
        q = "把大象放进冰箱需要几步"
        assert not message_targets_uploaded_skill(db, user, q, history)
        route = resolve_agent_route(db, user, q, chat_history=history)
        assert route.agent_id == "orchestrator"
    finally:
        db.close()
