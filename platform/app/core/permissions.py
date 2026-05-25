"""Feature (RBAC) and document-level permission checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPermission, PermissionLevel
from app.models.org import Permission, RolePermission, User, UserDepartment, UserRole

LEVEL_ALIASES: dict[str, str] = {
    PermissionLevel.read.value: PermissionLevel.visible.value,
    PermissionLevel.use.value: PermissionLevel.edit.value,
    PermissionLevel.delete.value: PermissionLevel.full.value,
}

LEVEL_ORDER: dict[str, int] = {
    PermissionLevel.visible.value: 1,
    PermissionLevel.query.value: 2,
    PermissionLevel.edit.value: 3,
    PermissionLevel.full.value: 4,
}

LEVEL_LABELS: dict[str, str] = {
    PermissionLevel.visible.value: "可见",
    PermissionLevel.query.value: "可查询",
    PermissionLevel.edit.value: "可编辑",
    PermissionLevel.full.value: "完全",
    PermissionLevel.read.value: "可见",
    PermissionLevel.use.value: "可编辑",
    PermissionLevel.delete.value: "完全",
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
    ("doc.personal.create", "个人级-新建"),
    ("doc.personal.edit", "个人级-编辑"),
    ("doc.personal.delete", "个人级-删除"),
]

DEFAULT_ROLES = {
    "sys_admin": {
        "name": "系统管理员",
        "permissions": [p[0] for p in CORE_PERMISSIONS],
    },
    "company_admin": {
        "name": "公司级管理员",
        "permissions": [
            "doc.read",
            "doc.grant",
            "doc.company.create",
            "doc.company.edit",
            "doc.company.delete",
            "doc.dept.create",
            "doc.dept.edit",
            "doc.dept.delete",
            "doc.personal.create",
            "doc.personal.edit",
            "doc.personal.delete",
        ],
    },
    "dept_admin": {
        "name": "部门管理员",
        "permissions": [
            "doc.read",
            "doc.grant",
            "doc.dept.create",
            "doc.dept.edit",
            "doc.dept.delete",
            "doc.personal.create",
            "doc.personal.edit",
            "doc.personal.delete",
        ],
    },
    "member": {
        "name": "普通成员",
        "permissions": [
            "doc.read",
            "doc.personal.create",
            "doc.personal.edit",
            "doc.personal.delete",
        ],
    },
}


def user_role_codes(db: Session, user_id: uuid.UUID) -> set[str]:
    from app.models.org import Role

    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return set(db.scalars(stmt).all())


def describe_user_tier(db: Session, user: User) -> str:
    """便于界面展示的用户层级（与 KnowFlow 知识库授权策略一致）。"""
    if user_is_superuser(db, user):
        return "system_admin"
    codes = user_role_codes(db, user.id)
    if "company_admin" in codes or "sys_admin" in codes:
        return "company_admin"
    if "dept_admin" in codes:
        return "dept_admin"
    return "member"


def user_permission_codes(db: Session, user_id: uuid.UUID) -> set[str]:
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return set(db.scalars(stmt).all())


def user_is_superuser(db: Session, user: User) -> bool:
    """系统管理员：默认 admin 账号或拥有 admin.user 权限的用户。"""
    if user.username == "admin":
        return True
    return "admin.user" in user_permission_codes(db, user.id)


def user_is_company_admin(db: Session, user: User) -> bool:
    if user_is_superuser(db, user):
        return True
    codes = user_role_codes(db, user.id)
    return "company_admin" in codes or "sys_admin" in codes


def user_is_dept_admin(db: Session, user: User) -> bool:
    if user_is_superuser(db, user):
        return True
    return "dept_admin" in user_role_codes(db, user.id)


def user_has_permission(db: Session, user: User, code: str) -> bool:
    if user_is_superuser(db, user):
        return True
    return code in user_permission_codes(db, user.id)


def user_dept_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(UserDepartment.dept_id).where(UserDepartment.user_id == user_id)
    return list(db.scalars(stmt).all())


def user_role_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(UserRole.role_id).where(UserRole.user_id == user_id)
    return list(db.scalars(stmt).all())


def can_access_document(
    db: Session,
    user: User,
    document: Document,
    required_level: str,
) -> bool:
    from app.core.document_scope import can_access_document as _scope_access

    return _scope_access(db, user, document, required_level)
