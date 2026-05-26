from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.config import get_settings
from app.core.exceptions import bad_request, forbidden, unauthorized
from app.core.permissions import user_dept_ids, user_permission_codes
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode_token,
    verify_password,
)
from app.database import get_db
from app.models.org import Role, User, UserRole
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.schemas.common import ApiResponse
from app.services.audit_service import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(db: Session, user: User, request: Request) -> TokenResponse:
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    write_audit(
        db,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    if get_settings().knowflow_enabled:
        try:
            from app.services.ragflow_identity_service import ensure_ragflow_account

            ensure_ragflow_account(db, user)
        except Exception:
            pass
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise unauthorized("Invalid username or password")
    if user.status != "active":
        raise unauthorized("User is disabled")
    return ApiResponse(data=_issue_tokens(db, user, request))


@router.post("/register", response_model=ApiResponse[TokenResponse])
def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    settings = get_settings()
    if not settings.allow_public_register:
        raise forbidden("Registration is disabled")

    username = body.username.strip()
    if username == settings.bootstrap_admin_username:
        raise bad_request("Username not available")
    if db.scalar(select(User).where(User.username == username)):
        raise bad_request("Username already exists")

    member_role = db.scalar(select(Role).where(Role.code == "member"))
    if not member_role:
        raise bad_request("Member role not configured")

    user = User(
        username=username,
        display_name=username,
        email=None,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=member_role.id, scope_dept_id=None))
    write_audit(
        db,
        user_id=user.id,
        action="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_issue_tokens(db, user, request))


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
def refresh_token(
    body: dict,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    token = body.get("refresh_token")
    if not token:
        raise unauthorized("refresh_token required")
    payload = safe_decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise unauthorized("Invalid refresh token")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or user.status != "active":
        raise unauthorized()
    return ApiResponse(
        data=TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )
    )


@router.get("/me", response_model=ApiResponse[MeResponse])
def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MeResponse]:
    return ApiResponse(
        data=MeResponse(
            id=user.id,
            username=user.username,
            display_name=user.username,
            email=user.email,
            permissions=sorted(user_permission_codes(db, user.id)),
            department_ids=user_dept_ids(db, user.id),
        )
    )
