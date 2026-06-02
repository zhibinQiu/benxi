"""平台内置 admin 账号（bootstrap）与系统管理员身份判定。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import bootstrap_login_id, is_bootstrap_login_id, login_ids_equal
from app.models.org import Role, User, UserRole

SYSTEM_ADMIN_ROLE_CODE = "sys_admin"


def is_bootstrap_admin(user: User) -> bool:
    """唯一系统管理员账号（phone=bootstrap_admin_phone），不可删除、不可改手机号。"""
    if not user.phone:
        return False
    return login_ids_equal(user.phone, bootstrap_login_id())


def normalize_bootstrap_login_id() -> str:
    return bootstrap_login_id()


def user_has_system_admin_role(db: Session, user_id: uuid.UUID) -> bool:
    """是否被授予「系统管理员」角色（由 admin 或其他系统管理员在用户管理中分配）。"""
    row = db.scalar(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Role.code == SYSTEM_ADMIN_ROLE_CODE,
        )
        .limit(1)
    )
    return row is not None


def ensure_bootstrap_has_system_admin_role(db: Session, user: User) -> None:
    """保证内置 admin 账号始终绑定 sys_admin 角色。"""
    if not is_bootstrap_admin(user):
        return
    if user_has_system_admin_role(db, user.id):
        return
    sys_role = db.scalar(select(Role).where(Role.code == SYSTEM_ADMIN_ROLE_CODE))
    if sys_role:
        db.add(UserRole(user_id=user.id, role_id=sys_role.id, scope_dept_id=None))
        db.flush()
