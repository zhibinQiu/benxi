"""AIP（GB/Z 185 智能体互联）对外发现与调用 API。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.aip_deps import AipAuthContext, resolve_aip_auth_context
from app.api.deps import get_client_ip
from app.api.streaming_utils import stream_sse_payloads
from app.config import get_settings
from app.database import get_db
from app.schemas.aip import (
    AipAgentDetailOut,
    AipDiscoverOut,
    AipInteractIn,
    AipInteractOut,
)
from app.schemas.common import ApiResponse
from app.services import aip_registry_service as aip_svc
from app.services.audit_service import write_audit

router = APIRouter(prefix="/aip", tags=["aip"])


def _audit_aip_call(
    db: Session,
    auth: AipAuthContext,
    *,
    action: str,
    detail: dict,
    client_ip: str | None,
) -> None:
    write_audit(
        db,
        user_id=auth.user.id,
        action=action,
        resource_type="aip",
        detail={
            **detail,
            "auth_mode": auth.mode,
            "sk_id": str(auth.secret_key.id) if auth.secret_key else None,
        },
        ip_address=client_ip,
    )


@router.get("/discover", response_model=ApiResponse[AipDiscoverOut])
def aip_discover(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    capability: Annotated[str | None, Query(description="能力 ID，如 cap:research")] = None,
    q: Annotated[str | None, Query(description="关键词")] = None,
    include_orchestrator: bool = False,
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipDiscoverOut]:
    from fastapi.security import HTTPAuthorizationCredentials

    creds = None
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_header.split(" ", 1)[1]
        )
    auth = resolve_aip_auth_context(db, request, creds)
    settings = get_settings()
    if not settings.aip_enabled:
        return ApiResponse(data=AipDiscoverOut(total=0, items=[]))
    _audit_aip_call(
        db,
        auth,
        action="aip.discover",
        detail={"capability": capability, "q": q},
        client_ip=client_ip,
    )
    return ApiResponse(
        data=aip_svc.discover_agents(
            db,
            capability=capability,
            q=q,
            include_orchestrator=include_orchestrator,
        )
    )


@router.get("/agents/{aid:path}", response_model=ApiResponse[AipAgentDetailOut])
def aip_read_agent(
    aid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipAgentDetailOut]:
    from fastapi.security import HTTPAuthorizationCredentials

    creds = None
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_header.split(" ", 1)[1]
        )
    auth = resolve_aip_auth_context(db, request, creds)
    decoded = unquote(aid).strip()
    _audit_aip_call(
        db,
        auth,
        action="aip.read_agent",
        detail={"aid": decoded},
        client_ip=client_ip,
    )
    return ApiResponse(data=aip_svc.get_agent_by_aid(db, decoded))


@router.post("/interact", response_model=ApiResponse[AipInteractOut])
async def aip_interact(
    body: AipInteractIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipInteractOut]:
    from fastapi.security import HTTPAuthorizationCredentials

    creds = None
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_header.split(" ", 1)[1]
        )
    auth = resolve_aip_auth_context(
        db, request, creds, body_auth_token=body.auth_token
    )
    if not body.source_aid and auth.source_aid:
        body = body.model_copy(update={"source_aid": auth.source_aid})
    result = await aip_svc.interact_with_agent(db, auth.user, body)
    _audit_aip_call(
        db,
        auth,
        action="aip.interact",
        detail={
            "target_aid": body.target_aid,
            "satisfied": result.satisfied,
        },
        client_ip=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/interact/stream")
async def aip_interact_stream(
    body: AipInteractIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> StreamingResponse:
    from fastapi.security import HTTPAuthorizationCredentials

    creds = None
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_header.split(" ", 1)[1]
        )
    auth = resolve_aip_auth_context(
        db, request, creds, body_auth_token=body.auth_token
    )
    if not body.source_aid and auth.source_aid:
        body = body.model_copy(update={"source_aid": auth.source_aid})
    _audit_aip_call(
        db,
        auth,
        action="aip.interact_stream",
        detail={"target_aid": body.target_aid},
        client_ip=client_ip,
    )

    async def payloads():
        async for chunk in aip_svc.iter_interact_with_agent_stream(
            db, auth.user, body
        ):
            yield chunk

    return StreamingResponse(
        stream_sse_payloads(db, payloads),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
