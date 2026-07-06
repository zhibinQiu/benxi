"""平台 Agent 原子工具目录 — 与 ToolCenter 注册表对齐。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.tool_skill_taxonomy import GLOBAL_ATOMIC_TOOL_NAMES, ToolCategory, _TOOL_CATEGORIES
from app.models.org import User
from app.schemas.agent_skill import AgentToolCategoryOut, AgentToolOut, RateLimitOut
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.tool_center.registry import get_tool_center


def _availability(db: Session, name: str, *, user: User | None) -> tuple[bool, str]:
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config

    if name == ATOMIC_TOOL_WEB_SEARCH:
        return True, ""
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        return True, ""
    if name == ATOMIC_TOOL_KG_QUERY:
        return True, ""
    if name.startswith("browser_") or name == "schedule_browser_workflow":
        if get_browser_rpa_config(db).enabled:
            return True, ""
        return False, "浏览器 RPA 未在系统设置中启用"
    return True, ""


def list_agent_tools(
    db: Session,
    *,
    user: User | None = None,
) -> list[AgentToolOut]:
    """返回 ToolCenter 全局原子工具（完整 ToolDescriptor）。"""
    items: list[AgentToolOut] = []
    for desc in get_tool_center().list_descriptors():
        if desc.tool_id not in GLOBAL_ATOMIC_TOOL_NAMES:
            continue
        category = _TOOL_CATEGORIES.get(desc.tool_id, ToolCategory.PLATFORM)
        available, note = _availability(db, desc.tool_id, user=user)
        items.append(
            AgentToolOut(
                name=desc.tool_id,
                tool_id=desc.tool_id,
                tool_type=desc.tool_type,
                description=desc.description,
                category=AgentToolCategoryOut(category.value),
                available=available,
                availability_note=note,
                input_schema=desc.input_schema,
                output_schema=desc.output_schema,
                rate_limit=RateLimitOut(qps=desc.rate_limit.qps),
                tool_version=desc.tool_version,
            )
        )
    return items
