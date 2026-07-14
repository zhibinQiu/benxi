"""agentkit-mcp — MCP 协议与客户端。

典型用法::

    from app.agentkit.mcp import McpClient, McpClientConfig

    client = McpClient(McpClientConfig(
        endpoint="https://mcp.example.com",
        client_name="my-app",
        client_version="1.0.0",
    ))
    tools = await client.list_tools()
    result = await client.call_tool("search", {"query": "hello"})
"""

__version__ = "4.6.0"

from app.agentkit.mcp.client import McpClient, McpClientConfig
from app.agentkit.mcp.protocol import (
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
