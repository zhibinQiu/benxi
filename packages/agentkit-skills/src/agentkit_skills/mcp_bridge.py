"""MCP Skill → SkillDefinition 桥接（通用，无 ORM / 无 httpx）。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentkit_skills.types import (
    SkillDefinition,
    SkillHandler,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
    SkillToolSpec,
)


class McpToolCaller(Protocol):
    """MCP 工具调用协议：宿主注入实现。"""

    async def __call__(
        self,
        endpoint: str,
        tool_name: str,
        params: dict[str, Any],
        auth_token: str,
        transport: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class McpSkillRecord:
    """外部 MCP Skill 登记项。"""

    name: str
    title: str
    description: str
    endpoint: str
    transport: str = "http"
    auth_token: str = ""
    enabled: bool = True
    tools_cache: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""


def summarize_mcp_tool_result(result: Any, *, max_len: int = 4000) -> str:
    """压缩 MCP tools/call 结果为短文本。"""
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


def make_mcp_tool_handler(
    record: McpSkillRecord,
    tool_name: str,
    *,
    call_tool: McpToolCaller,
    summary_limit: int = 4000,
) -> SkillHandler:
    """为单个 MCP 工具生成 Skill handler。"""

    async def handler(ctx: SkillInvocationContext, params: dict[str, Any]) -> SkillInvocationResult:
        del ctx
        try:
            result = await call_tool(
                record.endpoint,
                tool_name,
                dict(params or {}),
                record.auth_token,
                record.transport,
            )
        except Exception as exc:
            return SkillInvocationResult(
                ok=False,
                summary=f"MCP 工具 `{record.name}.{tool_name}` 调用失败",
                error=str(exc),
            )
        summary = summarize_mcp_tool_result(result, max_len=summary_limit)
        is_error = bool(isinstance(result, dict) and result.get("isError"))
        return SkillInvocationResult(
            ok=not is_error,
            summary=summary[:summary_limit] or f"MCP 工具 `{tool_name}` 已执行",
            data=result,
            error=summary if is_error else None,
        )

    return handler


def build_mcp_skill_definition(
    record: McpSkillRecord,
    *,
    call_tool: McpToolCaller,
) -> SkillDefinition:
    """将 MCP 登记项转换为可注册的 SkillDefinition。"""
    tools: list[SkillToolSpec] = []
    for raw in record.tools_cache:
        tool_name = str(raw.get("name") or "").strip()
        if not tool_name:
            continue
        schema = raw.get("inputSchema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        tools.append(
            SkillToolSpec(
                name=tool_name,
                description=str(raw.get("description") or f"MCP 工具 {tool_name}"),
                parameters=schema,
                handler=make_mcp_tool_handler(record, tool_name, call_tool=call_tool),
            )
        )
    readiness = SkillReadiness.STUB
    if record.enabled and tools:
        readiness = SkillReadiness.READY
    return SkillDefinition(
        name=record.name,
        title=record.title or record.name,
        description=record.description or f"外部 MCP Skill `{record.name}`",
        source=SkillSource.MCP,
        tools=tuple(tools),
        readiness=readiness,
        source_type=record.transport,
        catalog_visible=True,
        catalog_tier="extended",
        use_when=record.use_when or record.description,
        dont_use_when=record.dont_use_when,
        output=record.output or "按 MCP 工具返回内容作答",
    )
