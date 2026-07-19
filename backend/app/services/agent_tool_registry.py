"""平台 Agent 原子工具目录 — 与 ToolCenter 注册表对齐。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.tool_skill_taxonomy import ToolCategory, _TOOL_CATEGORIES
from app.models.org import User
from app.schemas.agent_skill import AgentToolCategoryOut, AgentToolOut, RateLimitOut
from app.tool_center.registry import get_tool_center


def list_agent_tools(
    db: Session,
    *,
    user: User | None = None,
) -> list[AgentToolOut]:
    """返回 ToolCenter 全局原子工具（完整 ToolDescriptor）。"""
    items: list[AgentToolOut] = []
    for desc in get_tool_center().list_descriptors():
        category = _TOOL_CATEGORIES.get(desc.tool_id, ToolCategory.PLATFORM)
        items.append(
            AgentToolOut(
                name=desc.tool_id,
                tool_id=desc.tool_id,
                description=desc.description,
                doc_text=desc.doc_text,
                category=AgentToolCategoryOut(category.value),
                input_schema=desc.input_schema,
                output_schema=desc.output_schema,
                rate_limit=RateLimitOut(qps=desc.rate_limit.qps),
                tool_version=desc.tool_version,
            )
        )
    return items
