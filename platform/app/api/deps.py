from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import forbidden, unauthorized
from app.core.permissions import user_has_permission
from app.core.security import safe_decode_token
from app.database import get_db
from app.models.org import User
from app.services.auth_session_service import (
    touch_user_last_seen_async,
    validate_token_version,
)

bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None,
) -> str | None:
    if creds and creds.credentials:
        return creds.credentials
    return request.query_params.get("token") or request.query_params.get("access_token")


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    raw = _resolve_token(request, creds)
    if not raw:
        raise unauthorized()
    payload = safe_decode_token(raw)
    if not payload or payload.get("type") != "access":
        raise unauthorized("Invalid access token")
    sub = payload.get("sub")
    if not sub:
        raise unauthorized()
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise unauthorized()
    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise unauthorized("User disabled or not found")
    validate_token_version(user, payload)
    touch_user_last_seen_async(user.id)
    return user


def require_permission(code: str):
    def _checker(
        db: Annotated[Session, Depends(get_db)],
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not user_has_permission(db, user, code):
            raise forbidden(f"Missing permission: {code}")
        return user

    return _checker


def require_any_permission(*codes: str):
    def _checker(
        db: Annotated[Session, Depends(get_db)],
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if any(user_has_permission(db, user, code) for code in codes):
            return user
        raise forbidden(f"Missing permission (any of): {', '.join(codes)}")

    return _checker


def require_feature(feature_id: str):
    """按功能插件 ID 校验权限（请求时解析，避免插件尚未注册）。"""

    def _checker(
        db: Annotated[Session, Depends(get_db)],
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        from app.features.registry import ensure_plugins_loaded, get_plugin

        ensure_plugins_loaded()
        plugin = get_plugin(feature_id)
        if not plugin:
            raise forbidden(f"Unknown feature: {feature_id}")
        if not user_has_permission(db, user, plugin.permission_code):
            raise forbidden(f"Missing permission: {plugin.permission_code}")
        return user

    return _checker


def get_client_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None
