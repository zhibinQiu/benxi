"""MCP Skill 对外 API — 平台 Skill 暴露与发现。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.aip_deps import resolve_aip_auth_context
from app.config import get_settings
from app.core.exceptions import service_unavailable
from app.core.mcp.platform_server import handle_mcp_jsonrpc, resolve_mcp_service_endpoint
from app.core.mcp.protocol import MCP_PROTOCOL_VERSION
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.mcp_external_skill import McpServerInfoOut

router = APIRouter(prefix="/mcp", tags=["mcp"])
_bearer = HTTPBearer(auto_error=False)


@router.get("/info", response_model=ApiResponse[McpServerInfoOut])
def mcp_info() -> ApiResponse[McpServerInfoOut]:
    settings = get_settings()
    return ApiResponse(
        data=McpServerInfoOut(
            enabled=bool(settings.mcp_enabled),
            endpoint=resolve_mcp_service_endpoint(),
            protocol_version=MCP_PROTOCOL_VERSION,
            description="平台 Skill MCP 网关：tools/list 暴露可调用 Skill；resources 暴露发展 Skill 的 SKILL.md。",
        )
    )


@router.post("")
async def mcp_post(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> JSONResponse:
    settings = get_settings()
    if not settings.mcp_enabled:
        raise service_unavailable("MCP 未启用")

    auth = resolve_aip_auth_context(db, request, creds)
    session_id = (request.headers.get("Mcp-Session-Id") or "").strip() or None

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
        )

    if isinstance(body, list):
        responses: list[dict[str, Any]] = []
        next_session = session_id
        for item in body:
            if not isinstance(item, dict):
                continue
            resp, next_session = await handle_mcp_jsonrpc(
                db,
                auth.user,
                item,
                session_id=next_session,
            )
            if resp.get("id") is not None or resp.get("error") or resp.get("result") is not None:
                responses.append(resp)
        headers = {}
        if next_session:
            headers["Mcp-Session-Id"] = next_session
        return JSONResponse(content=responses, headers=headers)

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}},
        )

    response, next_session = await handle_mcp_jsonrpc(
        db,
        auth.user,
        body,
        session_id=session_id,
    )
    headers = {}
    if next_session:
        headers["Mcp-Session-Id"] = next_session
    return JSONResponse(content=response, headers=headers)
