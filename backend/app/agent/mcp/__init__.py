"""app.agent.mcp — MCP 协议与客户端。

典型用法::

    from app.agent.mcp import McpClient, McpClientConfig

    client = McpClient(McpClientConfig(
        endpoint="https://mcp.example.com",
        client_name="my-app",
        client_version="1.0.0",
    ))
    tools = await client.list_tools()
    result = await client.call_tool("search", {"query": "hello"})
"""

from app.agent import __version__  # noqa: F401

from app.agent.mcp.client import McpClient, McpClientConfig
from app.agent.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    build_jsonrpc_notification,
    build_jsonrpc_request,
    jsonrpc_error,
    jsonrpc_result,
    mcp_text_content,
    parse_jsonrpc_response,
    summarize_mcp_tool_result,
)

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "McpClient",
    "McpClientConfig",
    "build_jsonrpc_notification",
    "build_jsonrpc_request",
    "jsonrpc_error",
    "jsonrpc_result",
    "mcp_text_content",
    "parse_jsonrpc_response",
    "summarize_mcp_tool_result",
]
