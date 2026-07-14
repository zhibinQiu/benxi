"""Supervisor 路由目录 — 专精智能体何时被调度、上下文延续判定。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.agent_profiles import get_agent_profile
from app.core.routing_catalog_md import (
    build_agents_catalog_text,
    load_agents_routing_md,
)
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_profile_service import is_agent_enabled

from app.services.agent_skill_router import is_skill_management_message


def message_targets_uploaded_skill(
    db: Session,
    user: User,
    message: str,
    chat_history: list[AiChatMessage] | None,
) -> bool:
    """仅 Skill 管理意图（创建/更新/删除）路由到技能开发专精（skill-dev）。
    提及技能名称但意图为「使用」时不触发此路由，交由正常技能评分路由处理。"""
    msg = (message or "").strip()
    if not msg:
        return False
    return is_skill_management_message(msg)


def build_supervisor_routing_catalog(
    db: Session,
    *,
    agent_ids: frozenset[str] | set[str] | None = None,
) -> str:
    """供调度 LLM 使用的专精目录 — 统一读取 agents.md。"""
    from app.core.agent_profiles import AGENT_PROFILES

    allowed = frozenset(agent_ids) if agent_ids else None
    enabled = frozenset(
        p.id
        for p in AGENT_PROFILES
        if p.id != "orchestrator"
        and is_agent_enabled(db, p.id)
        and (allowed is None or p.id in allowed)
    )
    return build_agents_catalog_text(enabled_ids=enabled)


def routing_catalog_for_agent(agent_id: str, db: Session) -> str | None:
    profile = get_agent_profile(agent_id)
    if not profile:
        return None
    entry = load_agents_routing_md().get(agent_id)
    if entry:
        parts = [entry.use_when, entry.dont_use_when, entry.output]
        return " ".join(p for p in parts if p).strip() or profile.description
    return profile.description
