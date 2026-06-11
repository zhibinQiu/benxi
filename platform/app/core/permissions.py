"""Feature (RBAC) and document-level permission checks."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, PermissionLevel
from app.models.org import Permission, RolePermission, User, UserRole

LEVEL_ALIASES: dict[str, str] = {
    PermissionLevel.read.value: PermissionLevel.visible.value,
    PermissionLevel.use.value: PermissionLevel.modify.value,
    PermissionLevel.edit.value: PermissionLevel.modify.value,
    PermissionLevel.full.value: PermissionLevel.modify.value,
    PermissionLevel.delete.value: PermissionLevel.modify.value,
}

LEVEL_ORDER: dict[str, int] = {
    PermissionLevel.visible.value: 0,
    PermissionLevel.query.value: 1,
    PermissionLevel.modify.value: 2,
}

LEVEL_LABELS: dict[str, str] = {
    PermissionLevel.visible.value: "可见",
    PermissionLevel.query.value: "可查",
    PermissionLevel.modify.value: "可修改",
    PermissionLevel.read.value: "可见",
    PermissionLevel.use.value: "可修改",
    PermissionLevel.edit.value: "可修改",
    PermissionLevel.full.value: "可修改",
    PermissionLevel.delete.value: "可修改",
}


def normalize_permission_level(level: str) -> str:
    raw = (level or "").strip().lower()
    return LEVEL_ALIASES.get(raw, raw)


def level_order(level: str) -> int:
    return LEVEL_ORDER.get(normalize_permission_level(level), 0)


def level_satisfies(granted: str, required: str) -> bool:
    return level_order(granted) >= level_order(required)

CORE_PERMISSIONS = [
    ("admin.user", "用户管理"),
    ("admin.dept", "部门管理"),
    ("admin.role", "角色管理"),
    ("admin.audit", "审计查看"),
    ("admin.settings", "系统设置"),
    ("doc.read", "文档查阅"),
    ("doc.use", "文档使用"),
    ("doc.delete", "文档删除"),
    ("doc.grant", "文档授权"),
    ("doc.company.create", "公司级-新建"),
    ("doc.company.edit", "公司级-编辑"),
    ("doc.company.delete", "公司级-删除"),
    ("doc.dept.create", "部门级-新建"),
    ("doc.dept.edit", "部门级-编辑"),
    ("doc.dept.delete", "部门级-删除"),
    ("doc.team.create", "小组级-新建"),
    ("doc.team.edit", "小组级-编辑"),
    ("doc.team.delete", "小组级-删除"),
    ("doc.personal.create", "个人级-新建"),
    ("doc.personal.edit", "个人级-编辑"),
    ("doc.personal.delete", "个人级-删除"),
]

DEFAULT_ROLES = {
    "sys_admin": {
        "name": "系统管理员",
        "permissions": [p[0] for p in CORE_PERMISSIONS],
    },
    "member": {
        "name": "普通用户",
        "permissions": [
            "doc.read",
            "doc.personal.create",
            "doc.personal.edit",
            "doc.personal.delete",
            "doc.dept.create",
            "doc.dept.edit",
            "doc.dept.delete",
            "doc.team.create",
            "doc.team.edit",
            "doc.team.delete",
            "doc.company.create",
            "doc.company.edit",
            "doc.company.delete",
        ],
    },
}


def user_role_codes(db: Session, user_id: uuid.UUID) -> set[str]:
    from app.core.request_user_cache import cached_per_request
    from app.models.org import Role

    def _load() -> set[str]:
        stmt = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return set(db.scalars(stmt).all())

    return cached_per_request(f"role_codes:{user_id}", _load)


def user_is_system_admin(db: Session, user: User) -> bool:
    """系统管理员：持有 sys_admin 角色（含唯一内置 bootstrap 账号）。"""
    from app.core.platform_admin import user_has_system_admin_role

    return user_has_system_admin_role(db, user.id)


def describe_user_tier(db: Session, user: User) -> str:
    """便于界面展示的用户层级（系统管理员 / 普通用户）。"""
    if user_is_system_admin(db, user):
        return "system_admin"
    return "member"


def user_permission_codes(db: Session, user_id: uuid.UUID) -> set[str]:
    from app.core.request_user_cache import cached_per_request

    def _load() -> set[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        return set(db.scalars(stmt).all())

    return cached_per_request(f"perm_codes:{user_id}", _load)


def user_is_superuser(db: Session, user: User) -> bool:
    """文档与全局最高权限（与系统管理员身份一致，保留旧名供各模块调用）。"""
    return user_is_system_admin(db, user)


def user_is_company_admin(db: Session, user: User) -> bool:
    """已废弃分级管理员；仅系统管理员视为公司级管理身份。"""
    return user_is_superuser(db, user)


def user_is_dept_admin(db: Session, user: User) -> bool:
    """已废弃分级管理员。"""
    return False


def user_has_permission(db: Session, user: User, code: str) -> bool:
    if user_is_superuser(db, user):
        return True
    return code in user_permission_codes(db, user.id)


def user_dept_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    from app.core.request_user_cache import cached_per_request
    from app.core.user_department import user_dept_ids as _user_dept_ids

    return cached_per_request(
        f"dept_ids:{user_id}",
        lambda: _user_dept_ids(db, user_id),
    )


def user_role_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    from app.core.request_user_cache import cached_per_request

    def _load() -> list[uuid.UUID]:
        stmt = select(UserRole.role_id).where(UserRole.user_id == user_id)
        return list(db.scalars(stmt).all())

    return cached_per_request(f"role_ids:{user_id}", _load)


def can_access_document(
    db: Session,
    user: User,
    document: Document,
    required_level: str,
) -> bool:
    from app.core.document_scope import can_access_document as _scope_access

    return _scope_access(db, user, document, required_level)
