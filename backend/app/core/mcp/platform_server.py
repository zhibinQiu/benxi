"""平台 MCP Server — 对外暴露内置/发展 Skill。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.core.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    jsonrpc_error,
    jsonrpc_result,
    mcp_text_content,
)
from app.models.org import User
from app.services.agent_skill_service import get_skill_file_content
from app.skills.catalog import list_all_skill_definitions
from app.skills.executor import invoke_skill_tool
from app.skills.types import SkillInvocationContext, SkillReadiness, SkillSource
from app.skills.types import SkillDefinition

_sessions: dict[str, dict[str, Any]] = {}


def resolve_mcp_service_endpoint() -> str:
    settings = get_settings()
    if settings.mcp_service_base_url.strip():
        return settings.mcp_service_base_url.rstrip("/")
    if settings.aip_service_base_url.strip():
        base = settings.aip_service_base_url.rstrip("/")
        prefix = settings.api_prefix.rstrip("/")
        return f"{base}{prefix}/mcp"
    prefix = settings.api_prefix.rstrip("/")
    return f"{prefix}/mcp"


def _platform_tool_name(skill: SkillDefinition, tool_name: str) -> str:
    return f"{skill.name}.{tool_name}"


def _parse_platform_tool_name(full_name: str) -> tuple[str, str] | None:
    raw = (full_name or "").strip()
    if "." not in raw:
        return None
    skill_name, tool_name = raw.split(".", 1)
    if not skill_name or not tool_name:
        return None
    return skill_name, tool_name


def _iter_exposable_tools(
    db: Session,
    user: User,
) -> list[tuple[SkillDefinition, str, dict[str, Any]]]:
    skills = list_all_skill_definitions(
        db,
        user=user,
        admin_view=False,
        include_disabled=False,
        catalog_only=False,
    )
    out: list[tuple[SkillDefinition, str, dict[str, Any]]] = []
    for skill in skills:
        if skill.readiness != SkillReadiness.READY:
            continue
        if skill.source == SkillSource.UPLOADED:
            continue
        for tool in skill.tools:
            if not tool.handler:
                continue
            out.append((skill, tool.name, tool.parameters))
    return out


def _iter_exposable_resources(db: Session, user: User) -> list[dict[str, Any]]:
    skills = list_all_skill_definitions(
        db,
        user=user,
        admin_view=False,
        include_disabled=False,
        catalog_only=True,
    )
    resources: list[dict[str, Any]] = []
    for skill in skills:
        if skill.source != SkillSource.UPLOADED or not skill.skill_id:
            continue
        uri = f"skill://{skill.name}/SKILL.md"
        resources.append(
            {
                "uri": uri,
                "name": skill.name,
                "description": skill.description or skill.title,
                "mimeType": "text/markdown",
            }
        )
    return resources


async def handle_mcp_jsonrpc(
    db: Session,
    user: User,
    message: dict[str, Any],
    *,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """处理单条 MCP JSON-RPC 请求，返回 (响应体, 会话 ID)。"""
    request_id = message.get("id")
    method = str(message.get("method") or "").strip()
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if method == "initialize":
        new_session = uuid.uuid4().hex
        _sessions[new_session] = {"user_id": str(user.id)}
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": MCP_SERVER_NAME, "version": __version__},
            "instructions": "本析平台 Skill MCP 网关：tools 名为 `{skill}.{action}`。",
        }
        return jsonrpc_result(result, request_id), new_session

    if method in {"notifications/initialized", "initialized"}:
        return {"jsonrpc": "2.0"}, session_id

    active_session = session_id or ""
    if method != "initialize" and active_session and active_session not in _sessions:
        _sessions[active_session] = {"user_id": str(user.id)}

    if method == "tools/list":
        tools = []
        for skill, tool_name, schema in _iter_exposable_tools(db, user):
            tools.append(
                {
                    "name": _platform_tool_name(skill, tool_name),
                    "description": f"{skill.title} · {tool_name}",
                    "inputSchema": schema,
                }
            )
        return jsonrpc_result({"tools": tools}, request_id), session_id

    if method == "resources/list":
        resources = _iter_exposable_resources(db, user)
        return jsonrpc_result({"resources": resources}, request_id), session_id

    if method == "resources/read":
        uri = str(params.get("uri") or "").strip()
        if not uri.startswith("skill://") or not uri.endswith("/SKILL.md"):
            return (
                jsonrpc_error(-32602, f"不支持的 resource URI: {uri}", request_id),
                session_id,
            )
        skill_name = uri[len("skill://") : -len("/SKILL.md")]
        skill = next(
            (
                s
                for s in list_all_skill_definitions(
                    db, user=user, admin_view=False, include_disabled=False
                )
                if s.name == skill_name and s.source == SkillSource.UPLOADED and s.skill_id
            ),
            None,
        )
        if skill is None or not skill.skill_id:
            return jsonrpc_error(-32602, f"Skill 不存在: {skill_name}", request_id), session_id
        file_out = get_skill_file_content(db, skill.skill_id, "SKILL.md")
        payload = {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": file_out.text or "",
                }
            ]
        }
        return jsonrpc_result(payload, request_id), session_id

    if method == "tools/call":
        full_name = str(params.get("name") or "").strip()
        parsed = _parse_platform_tool_name(full_name)
        if parsed is None:
            return jsonrpc_error(-32602, f"无效 tool 名: {full_name}", request_id), session_id
        skill_name, tool_name = parsed
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        ctx = SkillInvocationContext(db=db, user=user)
        try:
            result = await invoke_skill_tool(
                ctx,
                skill_name=skill_name,
                tool_name=tool_name,
                params=arguments,
                admin_invoke=False,
            )
        except Exception as exc:
            return (
                jsonrpc_result(
                    mcp_text_content(str(exc), is_error=True),
                    request_id,
                ),
                session_id,
            )
        if not result.ok:
            return (
                jsonrpc_result(
                    mcp_text_content(result.summary or result.error or "Skill 调用失败", is_error=True),
                    request_id,
                ),
                session_id,
            )
        text = result.summary
        if result.data is not None:
            text = f"{text}\n\n{result.data}" if text else str(result.data)
        return jsonrpc_result(mcp_text_content(text or "ok"), request_id), session_id

    if request_id is None:
        return {"jsonrpc": "2.0"}, session_id
    return jsonrpc_error(-32601, f"Method not found: {method}", request_id), session_id
