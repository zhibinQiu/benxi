"""MCP JSON-RPC 2.0 协议常量与响应解析。

本模块无 I/O 依赖，可在任意环境做单元测试或嵌入自定义传输层。
"""

from __future__ import annotations

import json
import re
from typing import Any

# MCP 协议版本（与 2024-11-05 规范对齐）
MCP_PROTOCOL_VERSION = "2024-11-05"


def build_jsonrpc_request(
    request_id: str | int,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 JSON-RPC 2.0 请求体。"""
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def build_jsonrpc_notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造 JSON-RPC 通知（无 id 字段）。"""
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def parse_jsonrpc_response(body: str) -> dict[str, Any]:
    """解析 JSON 或 SSE ``event: message`` 响应体，返回最后一个有效 JSON-RPC 对象。"""
    text = (body or "").strip()
    if not text:
        raise ValueError("MCP 响应为空")
    if text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, list):
            for item in reversed(data):
                if isinstance(item, dict) and ("result" in item or "error" in item):
                    return item
            raise ValueError("MCP 批响应无有效 result/error")
        if isinstance(data, dict):
            return data
        raise ValueError("MCP 响应格式无效")
    messages = _parse_sse_messages(text)
    if not messages:
        raise ValueError("MCP SSE 响应无 message 事件")
    return messages[-1]


def _parse_sse_messages(text: str) -> list[dict[str, Any]]:
    """从 SSE 文本中提取 ``data:`` 行的 JSON 对象。"""
    out: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", text):
        data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        try:
            parsed = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def jsonrpc_error(code: int, message: str, request_id: str | int | None = None) -> dict[str, Any]:
    """构造 JSON-RPC error 响应（供 MCP Server 实现使用）。"""
    payload: dict[str, Any] = {"jsonrpc": "2.0", "error": {"code": code, "message": message}}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def jsonrpc_result(result: Any, request_id: str | int | None) -> dict[str, Any]:
    """构造 JSON-RPC result 响应（供 MCP Server 实现使用）。"""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def mcp_text_content(text: str, *, is_error: bool = False) -> dict[str, Any]:
    """构造 MCP ``tools/call`` 标准 text content 结果。"""
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        payload["isError"] = True
    return payload


def summarize_mcp_tool_result(result: Any, *, max_len: int = 4000) -> str:
    """将 MCP 工具返回值压缩为 LLM 可消费的短文本（节约 token）。"""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = [
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return joined[:max_len]
        if result.get("isError"):
            return str(result.get("error") or "MCP 工具返回错误")[:max_len]
    return json.dumps(result, ensure_ascii=False)[:max_len]
