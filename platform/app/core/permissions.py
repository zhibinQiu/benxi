"""Feature (RBAC) and document-level permission checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPermission, PermissionLevel
from app.models.org import Permission, RolePermission, User, UserDepartment, UserRole

LEVEL_ORDER = {
    PermissionLevel.read.value: 1,
    PermissionLevel.use.value: 2,
    PermissionLevel.delete.value: 3,
}

CORE_PERMISSIONS = [
    ("admin.user", "用户管理"),
    ("admin.dept", "部门管理"),
    ("admin.role", "角色管理"),
    ("admin.audit", "审计查看"),
    ("doc.read", "文档查阅"),
    ("doc.use", "文档使用"),
    ("doc.delete", "文档删除"),
    ("doc.grant", "文档授权"),
]

DEFAULT_ROLES = {
    "sys_admin": {
        "name": "系统管理员",
        "permissions": [p[0] for p in CORE_PERMISSIONS],
    },
    "dept_admin": {
        "name": "部门管理员",
        "permissions": ["doc.read", "doc.use", "doc.delete", "doc.grant"],
    },
    "member": {
        "name": "普通成员",
        "permissions": ["doc.read", "doc.use"],
    },
}


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


def _level_satisfies(granted: str, required: str) -> bool:
    return LEVEL_ORDER.get(granted, 0) >= LEVEL_ORDER.get(required, 0)


def can_access_document(
    db: Session,
    user: User,
    document: Document,
    required_level: str,
) -> bool:
    if document.deleted_at is not None:
        return False

    if user_has_permission(db, user, "admin.user"):
        return True

    if document.owner_id == user.id:
        return True

    now = datetime.now(timezone.utc)
    dept_ids = user_dept_ids(db, user.id)
    role_ids = user_role_ids(db, user.id)

    conditions = [
        (DocumentPermission.subject_type == "user")
        & (DocumentPermission.subject_id == user.id),
    ]
    if dept_ids:
        conditions.append(
            (DocumentPermission.subject_type == "dept")
            & (DocumentPermission.subject_id.in_(dept_ids))
        )
    if role_ids:
        conditions.append(
            (DocumentPermission.subject_type == "role")
            & (DocumentPermission.subject_id.in_(role_ids))
        )
    stmt = select(DocumentPermission).where(
        DocumentPermission.document_id == document.id,
        or_(*conditions),
    )
    for perm in db.scalars(stmt).all():
        if perm.expires_at and perm.expires_at < now:
            continue
        if _level_satisfies(perm.level, required_level):
            return True

    return False
