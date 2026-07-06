"""MCP（Model Context Protocol）客户端与平台 Skill 暴露。"""

from app.core.mcp.client import mcp_call_tool, mcp_list_tools
from app.core.mcp.external_registry import (
    get_mcp_skill_record,
    list_mcp_skill_records,
    load_mcp_external_skills,
)
from app.core.mcp.platform_server import handle_mcp_jsonrpc
from app.core.mcp.skill_builder import build_mcp_skill_definition

__all__ = [
    "build_mcp_skill_definition",
    "get_mcp_skill_record",
    "handle_mcp_jsonrpc",
    "list_mcp_skill_records",
    "load_mcp_external_skills",
    "mcp_call_tool",
    "mcp_list_tools",
]
