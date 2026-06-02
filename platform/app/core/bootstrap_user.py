"""唯一内置系统管理员账号：归一化手机号、密码，并保证其持有 sys_admin 角色。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.phone import bootstrap_login_id, login_ids_equal
from app.core.platform_admin import (
    SYSTEM_ADMIN_ROLE_CODE,
    ensure_bootstrap_has_system_admin_role,
)
from app.core.security import hash_password
from app.models.org import Role, User, UserDepartment, UserRole

_LEGACY_BOOTSTRAP_PHONES = frozenset({"admin"})


def _find_bootstrap_user(db: Session, boot_phone: str) -> User | None:
    settings = get_settings()
    admin = db.scalar(select(User).where(User.phone == boot_phone))
    if admin:
        return admin
    for legacy in _LEGACY_BOOTSTRAP_PHONES:
        if legacy == boot_phone:
            continue
        admin = db.scalar(select(User).where(User.phone == legacy))
        if admin:
            return admin
    for key in (
        settings.bootstrap_admin_email,
        settings.bootstrap_admin_username,
        settings.bootstrap_admin_display_name,
    ):
        if not key:
            continue
        admin = db.scalar(select(User).where(User.email == key))
        if admin:
            return admin
        admin = db.scalar(select(User).where(User.username == key))
        if admin:
            return admin
        admin = db.scalar(select(User).where(User.display_name == key))
        if admin:
            return admin
    return None


def enforce_unique_bootstrap_admin(db: Session) -> None:
    """保证唯一 bootstrap 账号存在且持有 sys_admin；不撤销其他用户的 sys_admin。"""
    settings = get_settings()
    boot_phone = bootstrap_login_id()
    display = (
        settings.bootstrap_admin_display_name or settings.bootstrap_admin_username
    )

    admin = _find_bootstrap_user(db, boot_phone)
    if not admin:
        return

    prev_phone = (admin.phone or "").strip()
    admin.phone = boot_phone
    admin.display_name = display
    if not (admin.username or "").strip():
        admin.username = settings.bootstrap_admin_username or "admin"
    if not admin.email:
        admin.email = settings.bootstrap_admin_email
    if prev_phone in _LEGACY_BOOTSTRAP_PHONES or not login_ids_equal(
        prev_phone, boot_phone
    ):
        admin.password_hash = hash_password(settings.bootstrap_admin_password)

    db.query(UserDepartment).filter(UserDepartment.user_id == admin.id).delete()

    ensure_bootstrap_has_system_admin_role(db, admin)

    member_role = db.scalar(select(Role).where(Role.code == "member"))

    if member_role:
        for user in db.scalars(select(User)).all():
            if user.id == admin.id:
                continue
            roles = set(
                db.scalars(
                    select(UserRole.role_id).where(UserRole.user_id == user.id)
                ).all()
            )
            if not roles:
                db.add(UserRole(user_id=user.id, role_id=member_role.id))

    db.flush()
