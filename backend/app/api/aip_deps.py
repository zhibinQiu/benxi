"""AIP 对外 API 鉴权 — 用户 JWT 或 SK（GB/Z 185.3）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import _resolve_token, get_current_user
from app.agentkit.aip.auth import is_aip_sk_token
from app.core.aip.aid import orchestrator_aid
from app.database import get_db
from app.models.aip_secret_key import AipSecretKey
from app.models.org import User
from app.services.aip_secret_key_service import authenticate_secret_key

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AipAuthContext:
    """AIP 调用方身份上下文。"""

    mode: Literal["user", "sk"]
    user: User
    secret_key: AipSecretKey | None = None
    source_aid: str | None = None


def resolve_aip_auth_context(
    db: Session,
    request: Request,
    creds: HTTPAuthorizationCredentials | None,
    *,
    body_auth_token: str | None = None,
) -> AipAuthContext:
    """解析 Authorization 或 body.auth_token；SK 优先，否则回退平台用户 JWT。"""
    header_token = _resolve_token(request, creds)
    sk_candidate = None
    for candidate in (header_token, body_auth_token):
        if is_aip_sk_token(candidate):
            sk_candidate = candidate.strip()
            break

    if sk_candidate:
        row, user = authenticate_secret_key(db, sk_candidate)
        return AipAuthContext(
            mode="sk",
            user=user,
            secret_key=row,
            source_aid=orchestrator_aid(),
        )

    user = get_current_user(request, db, creds)
    return AipAuthContext(mode="user", user=user, source_aid=orchestrator_aid())


def get_aip_auth_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AipAuthContext:
    return resolve_aip_auth_context(db, request, creds)


def get_aip_auth_context_optional_body(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth_token: str | None = None,
) -> AipAuthContext:
    return resolve_aip_auth_context(db, request, creds, body_auth_token=auth_token)
