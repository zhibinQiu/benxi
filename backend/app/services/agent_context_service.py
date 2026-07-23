"""AI 智能体上下文组装 — 分层注入 Discovery / Activation / Runtime / Memory。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.agent_runtime import build_runtime_context, normalize_channel
from app.models.org import User
from app.services.agent_memory_service import (
    append_user_memory,
    build_memory_prompt_context,
    build_turn_memory_note,
)
from app.services.agent_skill_router import (
    extract_memory_note,
    should_write_memory,
)
from app.skills.catalog import build_agent_catalog_prompt
from app.services.assistant_knowledge import build_platform_knowledge


@dataclass(frozen=True, slots=True)
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
    """按层解析 prompt。ai-home 仅注入记忆/运行时；Skill 目录由各专精 hop 按需加载。"""
    runtime_context = build_runtime_context(
        channel=normalize_channel(channel),
        user=user,
        conversation_id=conversation_id,
    )
    memory_context = build_memory_prompt_context(user.id)
    if normalize_channel(channel) == "ai-home":
        return AgentPromptLayers(
            runtime_context=runtime_context,
            memory_context=memory_context,
        )
    skill_catalog = build_agent_catalog_prompt(db, user=user, admin_view=False, query=message, lazy=True, preview_limit=4)
    platform_knowledge = ""
    if _needs_platform_knowledge(message):
        platform_knowledge = build_platform_knowledge(db, user)
    return AgentPromptLayers(
        skill_catalog=skill_catalog,
        runtime_context=runtime_context,
        memory_context=memory_context,
        platform_knowledge=platform_knowledge,
    )


def maybe_write_user_memory(
    user_id: uuid.UUID,
    message: str,
    reply: str | None = None,
) -> bool:
    """系统层：每轮结束后写入对话摘要；用户显式要求「记住」时优先写入指定内容。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if should_write_memory(msg):
        note = extract_memory_note(msg)
        if note:
            return append_user_memory(user_id, f"用户要求记住：{note}")
    summary = build_turn_memory_note(msg, reply or "")
    if not summary:
        return False
    return append_user_memory(user_id, summary)


def _needs_platform_knowledge(message: str) -> bool:
    from app.services.agent_skill_router import is_platform_usage_message

    return is_platform_usage_message(message)
