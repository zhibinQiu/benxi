"""专精智能体路由目录与上下文匹配测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_routing_catalog import (
    build_supervisor_routing_catalog,
    history_suggests_uploaded_skill_task,
    message_targets_uploaded_skill,
)
from app.services.agent_supervisor import resolve_agent_route


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_history_suggests_uploaded_skill_task():
    history = [
        AiChatMessage(
            role="user",
            content="生成 skill 爬取 https://www.tanshichang.cn 碳价",
        ),
        AiChatMessage(
            role="assistant",
            content="已为您创建 carbon-market-price 技能。",
        ),
    ]
    assert history_suggests_uploaded_skill_task("北京", history)


def test_build_supervisor_routing_catalog_includes_descriptions():
    db = SessionLocal()
    try:
        text = build_supervisor_routing_catalog(db, agent_ids={"skill-dev", "research"})
        assert "skill-dev" in text
        assert "run_skill_script" in text or "Skill" in text
        assert "research" in text
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
