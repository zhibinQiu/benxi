from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.core.permissions import user_dept_ids
from app.core.security import hash_password
from app.database import get_db
from app.models.org import User, UserDepartment, UserRole
from app.schemas.common import ApiResponse
from app.schemas.org import UserCreate, UserOut, UserUpdate
from app.services.user_service import delete_user_account

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


def _try_provision_ragflow_account(db: Session, user: User) -> None:
    """创建/更新用户后，在 RAGFlow 注册对应账号（KnowFlow 懒加载 SSO 用）。"""
    if not get_settings().knowflow_enabled:
        return
    try:
        from app.services.ragflow_identity_service import ensure_ragflow_account

        ensure_ragflow_account(db, user)
    except Exception as e:
        logger.warning(
            "RAGFlow 开户失败（平台用户已保存）username=%s: %s",
            user.username,
            e,
        )


def _user_out(db: Session, user: User) -> UserOut:
    dept_ids = list(
        db.scalars(
            select(UserDepartment.dept_id).where(UserDepartment.user_id == user.id)
        ).all()
    )
    role_ids = list(
        db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)).all()
    )
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.username,
        email=user.email,
        status=user.status,
        created_at=user.created_at,
        department_ids=dept_ids,
        role_ids=role_ids,
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
    if db.scalar(select(User).where(User.username == body.username)):
        raise bad_request("Username already exists")
    user = User(
        username=body.username,
        display_name=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    for i, dept_id in enumerate(body.department_ids):
        db.add(
            UserDepartment(
                user_id=user.id, dept_id=dept_id, is_primary=(i == 0)
            )
        )
    for role_id in body.role_ids:
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
    if body.username is not None:
        existing = db.scalar(
            select(User).where(User.username == body.username, User.id != user.id)
        )
        if existing:
            raise bad_request("Username already exists")
        user.username = body.username
        user.display_name = body.username
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.email is not None:
        user.email = body.email
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise bad_request("Invalid status")
        user.status = body.status
    previous_dept_ids: list | None = None
    if body.department_ids is not None:
        previous_dept_ids = user_dept_ids(db, user.id)
        db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete()
        for i, dept_id in enumerate(body.department_ids):
            db.add(
                UserDepartment(
                    user_id=user.id, dept_id=dept_id, is_primary=(i == 0)
                )
            )
    if body.role_ids is not None:
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role_id in body.role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
    user.display_name = user.username
    db.flush()
    if previous_dept_ids is not None and get_settings().knowflow_enabled:
        from app.services.ragflow_scope_service import reconcile_dept_membership_kb

        try:
            reconcile_dept_membership_kb(
                db, user, previous_dept_ids=previous_dept_ids
            )
        except Exception as e:
            logger.warning("部门变动 KnowFlow 授权同步失败 %s: %s", user.username, e)
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
    settings = get_settings()
    user = db.get(User, user_id)
    if not user:
        raise not_found("User not found")
    if user.id == current.id:
        raise bad_request("不能删除当前登录用户")
    if user.username == settings.bootstrap_admin_username:
        raise bad_request("不能删除系统默认管理员")
    if get_settings().knowflow_enabled:
        from app.services.ragflow_scope_service import revoke_all_dept_kb_grants

        try:
            revoke_all_dept_kb_grants(db, user)
        except Exception as e:
            logger.warning("删除用户 KnowFlow 部门库回收失败 %s: %s", user.username, e)
    delete_user_account(db, user)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(user_id)})
