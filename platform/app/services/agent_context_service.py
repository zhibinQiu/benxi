"""AI 智能体上下文组装 — 分层注入 Discovery / Activation / Runtime / Memory。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.agent_runtime import build_runtime_context, normalize_channel
from app.models.org import User
from app.services.agent_memory_service import append_user_memory, build_memory_prompt_context
from app.services.agent_skill_router import (
    extract_memory_note,
    should_write_memory,
)
from app.skills.catalog import build_agent_catalog_prompt
from app.services.assistant_knowledge import build_platform_knowledge


@dataclass(frozen=True)
class AgentPromptLayers:
    skill_catalog: str = ""
    activated_skills: str = ""
    runtime_context: str = ""
    memory_context: str = ""
    platform_knowledge: str = ""


def resolve_agent_prompt_layers(
    db: Session,
    user: User,
    message: str,
    *,
    channel: str = "ai-home",
    conversation_id: str | None = None,
) -> AgentPromptLayers:
    """按层解析 prompt：Discovery 描述符常驻，用户记忆每轮注入 system。"""
    runtime_context = build_runtime_context(
        channel=normalize_channel(channel),
        user=user,
        conversation_id=conversation_id,
    )
    skill_catalog = build_agent_catalog_prompt(db, user=user, admin_view=False)
    memory_context = build_memory_prompt_context(user.id)
    platform_knowledge = ""
    if _needs_platform_knowledge(message):
        platform_knowledge = build_platform_knowledge(db, user)
    return AgentPromptLayers(
        skill_catalog=skill_catalog,
        runtime_context=runtime_context,
        memory_context=memory_context,
        platform_knowledge=platform_knowledge,
    )


def maybe_write_user_memory(user_id: uuid.UUID, message: str) -> bool:
    """系统层：用户明确要求记住时写入 MEMORY.md。"""
    if not should_write_memory(message):
        return False
    note = extract_memory_note(message)
    return append_user_memory(user_id, note)


def _needs_platform_knowledge(message: str) -> bool:
    from app.services.agent_skill_router import is_platform_usage_message

    return is_platform_usage_message(message)
