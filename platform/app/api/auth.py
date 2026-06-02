from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.config import get_settings
from app.core.exceptions import bad_request, forbidden, unauthorized
from app.core.permissions import user_is_system_admin, user_permission_codes
from app.core.platform_admin import is_bootstrap_admin
from app.core.user_identity import (
    email_taken,
    find_user_by_login_account,
    phone_taken,
    username_taken,
)
from app.core.phone import is_bootstrap_login_id
from app.core.user_department import user_department_id, user_dept_ids
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode_token,
    verify_password,
)
from app.database import get_db
from app.models.org import Department, Role, User, UserRole
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.common import ApiResponse
from app.services.audit_service import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _display_name(user: User) -> str:
    return (user.display_name or user.username or "").strip() or "用户"


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
            from app.domains.knowledge import knowledge

            knowledge.warm_on_login(db, user)
            db.flush()
        except Exception:
            pass
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    user = find_user_by_login_account(db, body.account)
    if not user or not verify_password(body.password, user.password_hash):
        raise unauthorized("手机号/姓名或密码错误")
    if user.status != "active":
        raise unauthorized("账号已禁用")
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

    phone = body.phone
    email = body.email
    if is_bootstrap_login_id(phone):
        raise bad_request("该登录号不可注册")
    if phone_taken(db, phone):
        raise bad_request("该手机号已注册")
    if email_taken(db, email):
        raise bad_request("该邮箱已注册")

    member_role = db.scalar(select(Role).where(Role.code == "member"))
    if not member_role:
        raise bad_request("Member role not configured")

    name = body.display_name.strip()
    if username_taken(db, name):
        raise bad_request("该姓名已被使用")
    user = User(
        phone=phone,
        username=name,
        display_name=name,
        email=email,
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


def _me_response(db: Session, user: User) -> MeResponse:
    name = _display_name(user)
    uname = (user.username or "").strip() or name
    role_rows = list(
        db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    role_names = [rname for (rname,) in role_rows]
    if is_bootstrap_admin(user) and "系统管理员" not in role_names:
        role_names = ["系统管理员", *role_names]
    dept_id = user_department_id(db, user.id)
    dept_name = None
    if dept_id:
        dept = db.get(Department, dept_id)
        dept_name = dept.name if dept else None
    return MeResponse(
        id=user.id,
        phone=user.phone,
        display_name=name,
        username=uname,
        email=user.email,
        permissions=sorted(user_permission_codes(db, user.id)),
        department_id=dept_id,
        department_ids=user_dept_ids(db, user.id),
        department_name=dept_name,
        role_names=role_names,
        is_bootstrap_admin=is_bootstrap_admin(user),
        is_system_admin=user_is_system_admin(db, user),
    )


@router.get("/me", response_model=ApiResponse[MeResponse])
def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MeResponse]:
    return ApiResponse(data=_me_response(db, user))


@router.patch("/me", response_model=ApiResponse[MeResponse])
def update_me(
    body: ProfileUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MeResponse]:
    if body.display_name is not None:
        name = body.display_name.strip()
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的姓名")
        if username_taken(db, name, exclude_user_id=user.id):
            raise bad_request("该姓名已被使用")
        user.display_name = name
        user.username = name
    if body.email is not None:
        if email_taken(db, body.email, exclude_user_id=user.id):
            raise bad_request("该邮箱已被使用")
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_me_response(db, user))
