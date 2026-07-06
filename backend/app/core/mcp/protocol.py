"""MCP JSON-RPC 协议 — agentkit 再导出 + 平台命名常量。"""

from agentkit_mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    build_jsonrpc_notification,
    build_jsonrpc_request,
    jsonrpc_error,
    jsonrpc_result,
    mcp_text_content,
    parse_jsonrpc_response,
    summarize_mcp_tool_result,
)

MCP_CLIENT_NAME = "benxi-platform"
MCP_SERVER_NAME = "benxi-platform-skills"

__all__ = [
    "MCP_CLIENT_NAME",
    "MCP_PROTOCOL_VERSION",
    "MCP_SERVER_NAME",
    "build_jsonrpc_notification",
    "build_jsonrpc_request",
    "jsonrpc_error",
    "jsonrpc_result",
    "mcp_text_content",
    "parse_jsonrpc_response",
    "summarize_mcp_tool_result",
]
