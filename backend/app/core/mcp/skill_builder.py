"""将外部 MCP Skill 登记项转换为平台 SkillDefinition — agentkit 适配。"""

from __future__ import annotations

from typing import Any

from agentkit_skills.mcp_bridge import McpSkillRecord
from agentkit_skills.mcp_bridge import build_mcp_skill_definition as _build_mcp_skill

from app.core.mcp.client import mcp_call_tool
from app.core.mcp.external_registry import McpExternalSkillRecord
from app.skills.types import SkillDefinition


async def _platform_mcp_call_tool(
    endpoint: str,
    tool_name: str,
    params: dict[str, Any],
    auth_token: str,
    transport: str,
) -> dict[str, Any]:
    return await mcp_call_tool(
        endpoint,
        tool_name,
        params,
        auth_token=auth_token,
        transport=transport,
    )


def _to_mcp_record(record: McpExternalSkillRecord) -> McpSkillRecord:
    return McpSkillRecord(
        name=record.name,
        title=record.title,
        description=record.description,
        endpoint=record.endpoint,
        transport=record.transport,
        auth_token=record.auth_token,
        enabled=record.enabled,
        tools_cache=record.tools_cache,
        use_when=record.use_when,
        dont_use_when=record.dont_use_when,
        output=record.output,
    )


def build_mcp_skill_definition(record: McpExternalSkillRecord) -> SkillDefinition:
    return _build_mcp_skill(_to_mcp_record(record), call_tool=_platform_mcp_call_tool)
