"""MCP HTTP/SSE 客户端 — agentkit 适配层。"""

from __future__ import annotations

from typing import Any

from app.agentkit.mcp import McpClient, McpClientConfig

from app import __version__
from app.core.mcp.protocol import MCP_CLIENT_NAME, summarize_mcp_tool_result


def _make_client(
    endpoint: str,
    *,
    auth_token: str = "",
    transport: str = "http",
    list_timeout_sec: float = 60.0,
    call_timeout_sec: float = 120.0,
) -> McpClient:
    return McpClient(
        McpClientConfig(
            endpoint=endpoint,
            client_name=MCP_CLIENT_NAME,
            client_version=__version__,
            auth_token=auth_token,
            transport=transport,
            list_timeout_sec=list_timeout_sec,
            call_timeout_sec=call_timeout_sec,
        )
    )


async def mcp_open_session(
    endpoint: str,
    *,
    auth_token: str = "",
    transport: str = "http",
    timeout_sec: float = 60.0,
) -> str | None:
    """initialize + initialized 通知；返回会话 ID（若有）。"""
    return await _make_client(
        endpoint,
        auth_token=auth_token,
        transport=transport,
        list_timeout_sec=timeout_sec,
        call_timeout_sec=timeout_sec,
    ).open_session()


async def mcp_list_tools(
    endpoint: str,
    *,
    auth_token: str = "",
    transport: str = "http",
    timeout_sec: float = 60.0,
) -> list[dict[str, Any]]:
    return await _make_client(
        endpoint,
        auth_token=auth_token,
        transport=transport,
        list_timeout_sec=timeout_sec,
    ).list_tools()


async def mcp_call_tool(
    endpoint: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    auth_token: str = "",
    transport: str = "http",
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    return await _make_client(
        endpoint,
        auth_token=auth_token,
        transport=transport,
        call_timeout_sec=timeout_sec,
    ).call_tool(tool_name, arguments)


__all__ = [
    "mcp_call_tool",
    "mcp_list_tools",
    "mcp_open_session",
    "summarize_mcp_tool_result",
]
