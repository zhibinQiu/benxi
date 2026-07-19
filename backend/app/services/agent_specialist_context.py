"""专精智能体对话上下文组装 — Supervisor 与 AIP 执行层共用。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.agent_resident import build_specialist_resident_prompt
from app.core.agent_runtime import build_runtime_context
from app.core.prompt_budget import build_bounded_chat_messages
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_context_service import _needs_platform_knowledge, build_platform_knowledge
from app.services.agent_memory_service import build_memory_prompt_context
from app.services.agent_profile_service import (
    resolve_agent_instruction_body,
    resolve_agent_skill_names,
)
from app.skills.catalog import build_agent_catalog_prompt


def build_specialist_chat_messages(
    db: Session,
    user: User,
    *,
    agent_id: str,
    message: str,
    history: list[AiChatMessage] | None,
    retrieval_context: str = "",
    context_instruction: str = "",
    task_mode: bool = False,
    route_reason: str = "",
    skill_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """为指定专精智能体构建 bounded chat messages（system + history + user）。

    route_reason: 路由层分配的该智能体被选中的原因（如 "Skill 匹配（`web-search`）"），
                  会注入到 system prompt 的顶部以指导智能体优先使用哪类工具。

    skill_names: 可选预解析的 skill 名称列表，避免内部重复查询。
    """
    skill_names = skill_names if skill_names is not None else resolve_agent_skill_names(db, agent_id)
    if agent_id == "skill-dev":
        skill_catalog = build_agent_catalog_prompt(
            db,
            user=user,
            resident_only=False,
            lazy=False,
        )
    else:
        skill_catalog = build_agent_catalog_prompt(
            db,
            user=user,
            skill_names=skill_names,
            query=message,
            lazy=True,
            preview_limit=4,
        )
    platform_knowledge = ""
    if agent_id == "platform" and _needs_platform_knowledge(message):
        platform_knowledge = build_platform_knowledge(db, user)

    trimmed_history = list(history or [])
    if agent_id != "orchestrator" and len(trimmed_history) > 6:
        trimmed_history = trimmed_history[-6:]

    config_body = resolve_agent_instruction_body(db, agent_id)
    memory_context = build_memory_prompt_context(user.id)

    return build_bounded_chat_messages(
        system=build_specialist_resident_prompt(
            agent_id, config_body=config_body, task_mode=task_mode
        ),
        history=trimmed_history,
        user_message=message,
        retrieval_context=retrieval_context,
        platform_knowledge=platform_knowledge,
        skill_catalog=skill_catalog,
        memory_context=memory_context,
        runtime_context=build_runtime_context(channel=agent_id, user=user),
        context_instruction=context_instruction or "",
        route_reason=route_reason,
    )
