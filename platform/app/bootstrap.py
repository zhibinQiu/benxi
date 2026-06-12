"""Seed permissions, roles, and default admin user on first startup."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import CORE_PERMISSIONS, DEFAULT_ROLES
from app.core.security import hash_password
from app.features.registry import all_plugins, ensure_plugins_loaded, feature_permission_codes
from app.models.org import (
    Permission,
    Role,
    RolePermission,
    User,
    UserDepartment,
    UserRole,
)


def all_default_permissions() -> list[tuple[str, str]]:
    ensure_plugins_loaded()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for code, name in CORE_PERMISSIONS + feature_permission_codes():
        if code not in seen:
            seen.add(code)
            out.append((code, name))
    return out


def bootstrap_db(db: Session) -> None:
    ensure_plugins_loaded()
    _seed_permissions_and_roles(db)
    _sync_plugin_role_grants(db)
    _seed_admin(db)


def _seed_permissions_and_roles(db: Session) -> None:
    code_to_perm: dict[str, Permission] = {}
    for code, name in all_default_permissions():
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if not perm:
            perm = Permission(code=code, name=name)
            db.add(perm)
            db.flush()
        elif perm.name != name:
            perm.name = name
        code_to_perm[code] = perm

    for role_code, spec in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.code == role_code))
        if not role:
            role = Role(code=role_code, name=spec["name"])
            db.add(role)
            db.flush()
        existing = {
            rp.permission_id
            for rp in db.scalars(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).all()
        }
        for pcode in spec["permissions"]:
            perm = code_to_perm.get(pcode)
            if not perm:
                continue
            if perm.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.flush()


def _sync_plugin_role_grants(db: Session) -> None:
    """按插件 ``grant_to_roles`` 为角色补齐功能权限（升级兼容）。"""
    code_to_perm = {
        p.code: p
        for p in db.scalars(select(Permission)).all()
    }
    role_by_code = {r.code: r for r in db.scalars(select(Role)).all()}

    for plugin in all_plugins():
        perm = code_to_perm.get(plugin.permission_code)
        if not perm:
            continue
        target_roles = set(plugin.grant_to_roles) | {"sys_admin"}
        for role_code, role in role_by_code.items():
            should_have = role_code in target_roles
            rp = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if should_have and not rp:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            elif not should_have and rp:
                db.delete(rp)

    db.commit()


def _seed_admin(db: Session) -> None:
    from app.core.platform_admin import normalize_bootstrap_login_id

    settings = get_settings()
    boot_phone = normalize_bootstrap_login_id()
    display = (
        settings.bootstrap_admin_display_name or settings.bootstrap_admin_username
    )

    admin = db.scalar(select(User).where(User.phone == boot_phone))
    if not admin:
        admin = db.scalar(
            select(User).where(User.email == settings.bootstrap_admin_email)
        )
    if not admin:
        admin = db.scalar(
            select(User).where(User.username == settings.bootstrap_admin_username)
        )
    if not admin:
        admin = db.scalar(select(User).where(User.display_name == display))
    if not admin:
        admin = db.scalar(select(User).where(User.username == display))

    if admin:
        admin.display_name = display
        if not (admin.username or "").strip():
            admin.username = settings.bootstrap_admin_username or "admin"
        admin.phone = boot_phone
        db.query(UserDepartment).filter(UserDepartment.user_id == admin.id).delete()
        from app.core.platform_admin import ensure_bootstrap_has_system_admin_role

        ensure_bootstrap_has_system_admin_role(db, admin)
        db.commit()
        return

    admin = User(
        phone=boot_phone,
        username=settings.bootstrap_admin_username or "admin",
        display_name=display,
        email=settings.bootstrap_admin_email,
        password_hash=hash_password(settings.bootstrap_admin_password),
    )
    db.add(admin)
    db.flush()

    sys_role = db.scalar(select(Role).where(Role.code == "sys_admin"))
    if sys_role:
        db.add(UserRole(user_id=admin.id, role_id=sys_role.id, scope_dept_id=None))

    db.commit()
