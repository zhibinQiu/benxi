"""MCP HTTP/SSE 异步客户端。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from agentkit_mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    build_jsonrpc_notification,
    build_jsonrpc_request,
    parse_jsonrpc_response,
    summarize_mcp_tool_result,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class McpClientConfig:
    """MCP 客户端配置；所有字段均可由宿主应用注入，无全局状态。"""

    endpoint: str
    client_name: str = "agentkit-mcp"
    client_version: str = "0.1.0"
    auth_token: str = ""
    transport: str = "http"  # "http" | "sse"
    list_timeout_sec: float = 60.0
    call_timeout_sec: float = 120.0


class McpClient:
    """连接外部 MCP Server 的轻量客户端。

    一次 ``list_tools`` / ``call_tool`` 会自动完成 initialize 握手；
    如需复用会话，可在外部缓存 ``open_session()`` 返回的 session_id。
    """

    def __init__(self, config: McpClientConfig) -> None:
        self._cfg = config

    @property
    def config(self) -> McpClientConfig:
        return self._cfg

    async def open_session(self) -> str | None:
        """``initialize`` + ``notifications/initialized``；返回 ``Mcp-Session-Id``（若有）。"""
        request_id = uuid.uuid4().hex
        init_payload = build_jsonrpc_request(
            request_id,
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": self._cfg.client_name,
                    "version": self._cfg.client_version,
                },
            },
        )
        init_resp, session_id = await self._post_jsonrpc(
            init_payload,
            timeout_sec=self._cfg.list_timeout_sec,
        )
        self._raise_jsonrpc_error(init_resp)

        notify = build_jsonrpc_notification("notifications/initialized")
        try:
            _, session_id = await self._post_jsonrpc(
                notify,
                session_id=session_id,
                timeout_sec=self._cfg.list_timeout_sec,
            )
        except Exception:
            _logger.debug("MCP initialized 通知失败（部分 Server 可忽略） endpoint=%s", self._cfg.endpoint)
        return session_id

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出远端 MCP 工具定义（OpenAI function schema 兼容结构）。"""
        session_id = await self.open_session()
        payload = build_jsonrpc_request(uuid.uuid4().hex, "tools/list", {})
        response, _ = await self._post_jsonrpc(
            payload,
            session_id=session_id,
            timeout_sec=self._cfg.list_timeout_sec,
        )
        self._raise_jsonrpc_error(response)
        result = response.get("result") or {}
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            return []
        return [item for item in tools if isinstance(item, dict)]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用远端工具，返回 MCP ``tools/call`` result 字典。"""
        session_id = await self.open_session()
        payload = build_jsonrpc_request(
            uuid.uuid4().hex,
            "tools/call",
            {"name": tool_name, "arguments": dict(arguments or {})},
        )
        response, _ = await self._post_jsonrpc(
            payload,
            session_id=session_id,
            timeout_sec=self._cfg.call_timeout_sec,
        )
        self._raise_jsonrpc_error(response)
        result = response.get("result")
        if isinstance(result, dict):
            return result
        return {"content": [{"type": "text", "text": summarize_mcp_tool_result(result)}]}

    async def call_tool_text(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """调用工具并返回压缩后的纯文本（适合直接注入 LLM 上下文）。"""
        return summarize_mcp_tool_result(await self.call_tool(tool_name, arguments))

    async def _post_jsonrpc(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        timeout_sec: float = 60.0,
    ) -> tuple[dict[str, Any], str | None]:
        accept_sse = self._cfg.transport.strip().lower() == "sse"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream" if accept_sse else "application/json",
        }
        token = (self._cfg.auth_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            response = await client.post(self._cfg.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            new_session = response.headers.get("Mcp-Session-Id") or session_id
            parsed = parse_jsonrpc_response(response.text)
            return parsed, new_session

    @staticmethod
    def _raise_jsonrpc_error(payload: dict[str, Any]) -> None:
        err = payload.get("error")
        if isinstance(err, dict):
            raise RuntimeError(str(err.get("message") or "MCP JSON-RPC 错误"))
        if "result" not in payload:
            raise RuntimeError("MCP 响应缺少 result")
