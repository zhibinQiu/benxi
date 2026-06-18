from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.exceptions import bad_request, not_found
from app.core.permissions import user_dept_ids
from app.core.phone import is_bootstrap_login_id
from app.core.platform_admin import (
    SYSTEM_ADMIN_ROLE_CODE,
    ensure_bootstrap_has_system_admin_role,
    is_bootstrap_admin,
)
from app.core.security import hash_password
from app.core.user_department import (
    set_user_departments_or_bad_request,
    user_department_id,
)
from app.core.user_identity import email_taken, phone_taken, user_display_name, username_taken
from app.database import get_db
from app.models.org import Role, User, UserRole
from app.schemas.common import ApiResponse
from app.schemas.org import UserCreate, UserOut, UserUpdate
from app.services.user_service import delete_user_account

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


def _display_name(user: User) -> str:
    return user_display_name(user)


def _try_provision_ragflow_account(db: Session, user: User) -> None:
    from app.domains.knowledge import knowledge

    if not knowledge.enabled():
        return
    try:
        knowledge.ensure_account(db, user)
    except Exception as e:
        logger.warning(
            "RAGFlow 开户失败（平台用户已保存）%s: %s",
            _display_name(user),
            e,
        )


def _user_out(db: Session, user: User) -> UserOut:
    pid = user_department_id(db, user.id)
    dept_ids = [pid] if pid else []
    role_rows = list(
        db.execute(
            select(UserRole.role_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    role_ids = [rid for rid, _ in role_rows]
    role_names = [rname for _, rname in role_rows]
    if is_bootstrap_admin(user) and "系统管理员" not in role_names:
        role_names = ["系统管理员", *role_names]
    name = _display_name(user)
    uname = (user.username or "").strip() or name
    return UserOut(
        id=user.id,
        phone=user.phone,
        display_name=name,
        username=uname,
        email=user.email,
        status=user.status,
        created_at=user.created_at,
        department_id=pid,
        department_ids=dept_ids,
        role_ids=role_ids,
        role_names=role_names,
    )


@router.get("", response_model=ApiResponse[list[UserOut]])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[list[UserOut]]:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return ApiResponse(data=[_user_out(db, u) for u in users])


@router.post("", response_model=ApiResponse[UserOut])
def create_user(
    body: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    if is_bootstrap_login_id(body.phone):
        raise bad_request("该登录号为系统保留")
    if phone_taken(db, body.phone):
        raise bad_request("该手机号已存在")
    if email_taken(db, body.email):
        raise bad_request("该邮箱已存在")
    name = body.display_name.strip()
    if username_taken(db, name):
        raise bad_request("该姓名已被使用")
    user = User(
        phone=body.phone,
        username=name,
        display_name=name,
        email=body.email,
        password_hash=hash_password(body.password),
        status=body.status,
    )
    db.add(user)
    db.flush()
    set_user_departments_or_bad_request(db, user.id, body.department_ids)
    member_role = db.scalar(select(Role).where(Role.code == "member"))
    role_ids = list(body.role_ids)
    if not role_ids and member_role:
        role_ids = [member_role.id]
    for role_id in role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))
    _try_provision_ragflow_account(db, user)
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))


@router.patch("/{user_id}", response_model=ApiResponse[UserOut])
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    user = db.get(User, user_id)
    if not user:
        raise not_found("User not found")
    if body.phone is not None:
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的手机号")
        if phone_taken(db, body.phone, exclude_user_id=user.id):
            raise bad_request("该手机号已被使用")
        user.phone = body.phone
    if body.display_name is not None:
        name = body.display_name.strip()
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的姓名")
        if username_taken(db, name, exclude_user_id=user.id):
            raise bad_request("该姓名已被使用")
        user.display_name = name
        user.username = name
    elif body.username is not None:
        name = body.username.strip()
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的姓名")
        if username_taken(db, name, exclude_user_id=user.id):
            raise bad_request("该姓名已被使用")
        user.username = name
        user.display_name = name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.email is not None:
        if email_taken(db, body.email, exclude_user_id=user.id):
            raise bad_request("该邮箱已被使用")
        user.email = body.email
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise bad_request("Invalid status")
        if is_bootstrap_admin(user) and body.status != "active":
            raise bad_request("不能禁用系统默认管理员")
        user.status = body.status
    previous_dept_ids: list | None = None
    if body.department_ids is not None:
        if is_bootstrap_admin(user) and body.department_ids:
            raise bad_request("系统默认管理员不归属任何部门")
        previous_dept_ids = user_dept_ids(db, user.id)
        set_user_departments_or_bad_request(db, user.id, body.department_ids)
    if body.role_ids is not None:
        role_ids = list(body.role_ids)
        sys_role = db.scalar(select(Role).where(Role.code == SYSTEM_ADMIN_ROLE_CODE))
        member_role = db.scalar(select(Role).where(Role.code == "member"))
        if sys_role and is_bootstrap_admin(user):
            if sys_role.id not in role_ids:
                role_ids.append(sys_role.id)
        if not role_ids and member_role:
            role_ids = [member_role.id]
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role_id in role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
        if is_bootstrap_admin(user):
            ensure_bootstrap_has_system_admin_role(db, user)
    db.flush()
    if previous_dept_ids is not None:
        from app.domains.knowledge import knowledge

        if knowledge.enabled():
            try:
                knowledge.reconcile_dept_membership_kb(
                    db, user, previous_dept_ids=previous_dept_ids
                )
            except Exception as e:
                logger.warning(
                    "部门变动 KnowFlow 授权同步失败 %s: %s", _display_name(user), e
                )
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))


@router.delete("/{user_id}", response_model=ApiResponse[dict])
def delete_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(get_current_user)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[dict]:
    user = db.get(User, user_id)
    if not user:
        raise not_found("User not found")
    if user.id == current.id:
        raise bad_request("不能删除当前登录用户")
    if is_bootstrap_admin(user):
        raise bad_request("不能删除系统默认管理员")
    delete_user_account(db, user)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(user_id)})
