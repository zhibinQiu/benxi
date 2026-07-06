"""Supervisor 路由目录 — 专精智能体何时被调度、上下文延续判定。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.agent_profiles import get_agent_profile
from app.core.routing_catalog_md import (
    build_agents_catalog_text,
    load_agents_routing_md,
)
from app.core.tool_skill_taxonomy import BUILTIN_SKILL_NAMES
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.core.conversation_turn_context import effective_history_for_context
from app.services.agent_planner import match_uploaded_skill_for_message, _skill_name_sets
from app.services.agent_profile_service import is_agent_enabled

from app.services.agent_routing_signals import matches_browser_intent
from app.services.agent_skill_router import is_skill_management_message


def message_targets_uploaded_skill(
    db: Session,
    user: User,
    message: str,
    chat_history: list[AiChatMessage] | None,
) -> bool:
    """Skill 管理或已绑定 uploaded skill 名称匹配（无领域词表）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if is_skill_management_message(msg):
        return True
    if matches_browser_intent(msg):
        return False

    all_skill_names = _skill_name_sets(db, user) or set()
    uploaded_names = all_skill_names - BUILTIN_SKILL_NAMES
    if not uploaded_names:
        return False

    return (
        match_uploaded_skill_for_message(
            msg,
            effective_history_for_context(msg, chat_history),
            uploaded_names=uploaded_names,
            exclude_research_context=True,
        )
        is not None
    )


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
