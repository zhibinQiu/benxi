"""Supervisor 路由目录 — 专精智能体何时被调度、上下文延续判定。"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.agent_profiles import AGENT_PROFILES, get_agent_profile
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_planner import match_uploaded_skill_for_message, _skill_name_sets
from app.services.agent_profile_service import _binding_map
from app.core.agent_config import get_effective_description

from app.services.agent_routing_signals import matches_browser_intent
from app.services.agent_skill_router import is_skill_management_message

_UPLOADED_SKILL_TASK_HISTORY_RE = re.compile(
    r"碳价|行情|价格|爬取|抓取|skill|技能|tanshichang|市场|run_skill|已创建|已为您创建",
    re.I,
)


def _history_snippet(history: list[AiChatMessage] | None, *, limit: int = 6) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-limit:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:200]
        if text:
            lines.append(f"{role}：{text}")
    return "\n".join(lines)


def history_suggests_uploaded_skill_task(
    message: str,
    chat_history: list[AiChatMessage] | None,
) -> bool:
    """短跟贴：上文刚创建/讨论上传型技能或数据爬取任务。"""
    msg = (message or "").strip()
    if not msg or len(msg) > 32:
        return False
    recent = _history_snippet(chat_history)
    if not recent:
        return False
    return bool(_UPLOADED_SKILL_TASK_HISTORY_RE.search(recent))


def message_targets_uploaded_skill(
    db: Session,
    user: User,
    message: str,
    chat_history: list[AiChatMessage] | None,
) -> bool:
    """当前诉求是否应由上传型 Skill（run_skill_script）完成。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if is_skill_management_message(msg):
        return True
    if matches_browser_intent(msg):
        return False

    _, uploaded_names = _skill_name_sets(db, user)
    if not uploaded_names:
        return history_suggests_uploaded_skill_task(msg, chat_history)

    return (
        match_uploaded_skill_for_message(
            msg,
            chat_history,
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
    """供调度 LLM 使用的专精智能体目录（含 effective description）。"""
    allowed = frozenset(agent_ids) if agent_ids else None
    bindings = _binding_map(db)
    lines: list[str] = []
    for profile in sorted(AGENT_PROFILES, key=lambda item: item.sort_order):
        if allowed is not None and profile.id not in allowed:
            continue
        binding = bindings.get(profile.id)
        config_md = binding.config_md if binding is not None else None
        desc = get_effective_description(profile, config_md)
        lines.append(f"- **{profile.id}**（{profile.title}）：{desc}")
    return "\n".join(lines)


def routing_catalog_for_agent(agent_id: str, db: Session) -> str | None:
    profile = get_agent_profile(agent_id)
    if not profile:
        return None
    bindings = _binding_map(db)
    binding = bindings.get(profile.id)
    config_md = binding.config_md if binding is not None else None
    return get_effective_description(profile, config_md)
