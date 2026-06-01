"""文档库分级（公司 / 部门 / 个人）与分级权限。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.permissions import (
    PermissionLevel,
    level_satisfies,
    normalize_permission_level,
    user_dept_ids,
    user_has_permission,
    user_is_company_admin,
    user_is_dept_admin,
    user_is_superuser,
)
from app.models.document import Document, DocumentPermission, DocumentStatus
from app.models.org import User

DocumentScope = str

SCOPE_COMPANY = "company"
SCOPE_DEPARTMENT = "department"
SCOPE_PERSONAL = "personal"

VALID_SCOPES = (SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PERSONAL)
# 文档库 Tab 展示顺序（我的 → 部门 → 公司 → 分享）
LIBRARY_TAB_SCOPES = (SCOPE_PERSONAL, SCOPE_DEPARTMENT, SCOPE_COMPANY)

SCOPE_LABELS = {
    SCOPE_COMPANY: "公司级",
    SCOPE_DEPARTMENT: "部门级",
    SCOPE_PERSONAL: "我的",
}

_SCOPE_PERM_PREFIX = {
    SCOPE_COMPANY: "doc.company",
    SCOPE_DEPARTMENT: "doc.dept",
    SCOPE_PERSONAL: "doc.personal",
}


def scope_perm(scope: str, action: str) -> str:
    prefix = _SCOPE_PERM_PREFIX.get(scope)
    if not prefix:
        raise ValueError(f"invalid scope: {scope}")
    return f"{prefix}.{action}"


def can_create_in_scope(db: Session, user: User, scope: str) -> bool:
    if scope not in VALID_SCOPES:
        return False
    if user_is_superuser(db, user):
        return True
    return user_has_permission(db, user, scope_perm(scope, "create"))


def can_edit_in_scope(db: Session, user: User, scope: str) -> bool:
    if user_is_superuser(db, user):
        return True
    return user_has_permission(db, user, scope_perm(scope, "edit"))


def can_delete_in_scope(db: Session, user: User, scope: str) -> bool:
    if user_is_superuser(db, user):
        return True
    return user_has_permission(db, user, scope_perm(scope, "delete"))


def can_manage_library_folders(
    db: Session,
    user: User,
    scope: str,
    *,
    dept_id: uuid.UUID | None = None,
) -> bool:
    """知识库文件夹新建/删除：个人库按 create 权限；公司/部门库需对应管理员或分级 create。"""
    if scope not in VALID_SCOPES:
        return False
    if user_is_superuser(db, user):
        return True
    if scope == SCOPE_PERSONAL:
        return can_create_in_scope(db, user, scope)
    if scope == SCOPE_COMPANY:
        return user_is_company_admin(db, user) or can_create_in_scope(db, user, scope)
    if scope == SCOPE_DEPARTMENT:
        if dept_id and dept_id in user_dept_ids(db, user.id):
            if user_is_dept_admin(db, user) or can_create_in_scope(db, user, scope):
                return True
        elif user_is_dept_admin(db, user) or can_create_in_scope(db, user, scope):
            return True
    return False


def _document_scope(doc: Document) -> str:
    s = (getattr(doc, "scope", None) or "").strip()
    if s in VALID_SCOPES:
        return s
    if doc.dept_id:
        return SCOPE_DEPARTMENT
    return SCOPE_PERSONAL


def _has_explicit_permission(
    db: Session, user: User, document: Document, required_level: str
) -> bool:
    from datetime import datetime, timezone

    from sqlalchemy import or_, select

    from app.core.permissions import user_role_ids

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
    required = normalize_permission_level(required_level)
    for perm in db.scalars(stmt).all():
        if perm.expires_at and perm.expires_at < now:
            continue
        if level_satisfies(perm.level, required):
            return True
    return False


def is_access_denied(db: Session, user: User, document: Document) -> bool:
    from sqlalchemy import select

    from app.models.document_workflow import DocumentAccessDenial

    row = db.scalar(
        select(DocumentAccessDenial.id).where(
            DocumentAccessDenial.document_id == document.id,
            DocumentAccessDenial.user_id == user.id,
        )
    )
    return row is not None


def can_manage_document(db: Session, user: User, document: Document) -> bool:
    """管理文档状态、删除、恢复（上传者、系统管理员、分级管理员）。"""
    if user_is_superuser(db, user):
        return True
    if document.owner_id == user.id:
        return True
    if _has_explicit_permission(db, user, document, PermissionLevel.full.value):
        return True
    scope = _document_scope(document)
    if scope in (SCOPE_COMPANY, SCOPE_DEPARTMENT):
        return can_edit_in_scope(db, user, scope)
    return False


def can_grant_document_permissions(db: Session, user: User, document: Document) -> bool:
    """显式文档授权：仅创建人与系统管理员（无需审核，即时生效）。"""
    if document.deleted_at is not None:
        return False
    if user_is_superuser(db, user):
        return True
    return document.owner_id == user.id


def can_manage_document_denials(db: Session, user: User, document: Document) -> bool:
    """禁止访问：创建人/系统管理员；部门/公司管理员可对下属机构内文档屏蔽默认可见。"""
    if document.deleted_at is not None:
        return False
    if user_is_superuser(db, user) or document.owner_id == user.id:
        return True

    scope = _document_scope(document)
    if scope == SCOPE_COMPANY:
        return can_edit_in_scope(db, user, SCOPE_COMPANY)
    if scope == SCOPE_DEPARTMENT:
        if document.dept_id and document.dept_id in user_dept_ids(db, user.id):
            return can_edit_in_scope(db, user, SCOPE_DEPARTMENT)
    return False


def can_manage_document_acl(db: Session, user: User, document: Document) -> bool:
    """兼容：任一类文档 ACL 管理权限。"""
    return can_grant_document_permissions(db, user, document) or can_manage_document_denials(
        db, user, document
    )


def owner_qualifies_for_scope_list(db: Session, document: Document) -> bool:
    """公司/部门库列表：仅展示由对应分级管理员（或系统管理员）上传的文档。"""
    from app.models.org import User

    owner = db.get(User, document.owner_id)
    if not owner:
        return False
    scope = _document_scope(document)
    if scope == SCOPE_COMPANY:
        return user_is_company_admin(db, owner)
    if scope == SCOPE_DEPARTMENT:
        if not document.dept_id:
            return False
        if not user_is_dept_admin(db, owner):
            return False
        return document.dept_id in user_dept_ids(db, owner.id)
    return True


def can_read_document(db: Session, user: User, document: Document) -> bool:
    if document.deleted_at is not None:
        return False
    if user_is_superuser(db, user):
        return True

    if document.status == DocumentStatus.disabled.value:
        if not can_manage_document(db, user, document):
            return False

    scope = _document_scope(document)
    if _has_explicit_permission(db, user, document, PermissionLevel.visible.value):
        return True

    if is_access_denied(db, user, document):
        return False

    if scope == SCOPE_PERSONAL:
        return document.owner_id == user.id

    if scope == SCOPE_DEPARTMENT:
        if document.owner_id == user.id:
            return True
        if document.dept_id and document.dept_id in user_dept_ids(db, user.id):
            return user_has_permission(db, user, "doc.read")
        return False

    if scope == SCOPE_COMPANY:
        return user_has_permission(db, user, "doc.read")

    return False


def readable_by_scope_default(db: Session, user: User, document: Document) -> bool:
    """不依赖显式授权时，是否因分级归属而默认可读（用于「分享」列表去重）。"""
    if document.deleted_at is not None:
        return False
    if is_access_denied(db, user, document):
        return False

    scope = _document_scope(document)
    if scope == SCOPE_PERSONAL:
        return document.owner_id == user.id
    if scope == SCOPE_DEPARTMENT:
        if document.owner_id == user.id:
            return True
        return bool(
            document.dept_id
            and document.dept_id in user_dept_ids(db, user.id)
            and user_has_permission(db, user, "doc.read")
        )
    if scope == SCOPE_COMPANY:
        return user_has_permission(db, user, "doc.read")
    return False


def can_query_document(db: Session, user: User, document: Document) -> bool:
    """可在知识问答 / KnowFlow 中检索该文档。"""
    if not can_read_document(db, user, document):
        return False
    if user_is_superuser(db, user):
        return True
    if _has_explicit_permission(db, user, document, PermissionLevel.query.value):
        return True
    if document.owner_id == user.id:
        return True
    if readable_by_scope_default(db, user, document):
        return True
    return can_edit_document(db, user, document)


def can_edit_document(db: Session, user: User, document: Document) -> bool:
    """可上传新版本、翻译、对比等（不含删除）。"""
    if not can_read_document(db, user, document):
        return False
    if user_is_superuser(db, user):
        return True
    if document.owner_id == user.id:
        return True
    if _has_explicit_permission(db, user, document, PermissionLevel.edit.value):
        return True

    scope = _document_scope(document)
    if scope in (SCOPE_COMPANY, SCOPE_DEPARTMENT):
        return can_edit_in_scope(db, user, scope)
    return False


def can_use_document(db: Session, user: User, document: Document) -> bool:
    """兼容旧名：等同 can_edit_document。"""
    return can_edit_document(db, user, document)


def can_delete_document(db: Session, user: User, document: Document) -> bool:
    """移入回收站：与 can_manage_document 一致（需文档未在回收站）。"""
    if document.deleted_at is not None:
        return False
    return can_manage_document(db, user, document)


def can_restore_document(db: Session, user: User, document: Document) -> bool:
    """从个人回收站恢复。"""
    if document.deleted_at is None:
        return False
    if document.deleted_by and document.deleted_by == user.id:
        return True
    return can_manage_document(db, user, document)


def effective_permission_level(db: Session, user: User, document: Document) -> str | None:
    """当前用户对该文档的综合能力档位（用于界面展示）。"""
    if can_delete_document(db, user, document):
        return PermissionLevel.full.value
    if can_edit_document(db, user, document):
        return PermissionLevel.edit.value
    if can_query_document(db, user, document):
        return PermissionLevel.query.value
    if can_read_document(db, user, document):
        return PermissionLevel.visible.value
    return None


def can_access_document(
    db: Session,
    user: User,
    document: Document,
    required_level: str,
) -> bool:
    level = normalize_permission_level(required_level)
    if level == PermissionLevel.visible.value:
        return can_read_document(db, user, document)
    if level == PermissionLevel.query.value:
        return can_query_document(db, user, document)
    if level == PermissionLevel.edit.value:
        return can_edit_document(db, user, document)
    if level == PermissionLevel.full.value:
        return can_delete_document(db, user, document)
    return False


def primary_dept_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    from sqlalchemy import select

    from app.models.org import UserDepartment

    ud = db.scalar(
        select(UserDepartment)
        .where(UserDepartment.user_id == user_id)
        .order_by(UserDepartment.is_primary.desc())
        .limit(1)
    )
    return ud.dept_id if ud else None


def resolve_create_params(
    db: Session, user: User, *, scope: str, dept_id: uuid.UUID | None
) -> tuple[str, uuid.UUID | None]:
    """校验新建权限并返回规范化 (scope, dept_id)。"""
    from app.core.exceptions import bad_request, forbidden

    if scope not in VALID_SCOPES:
        raise bad_request("无效的分级 scope")
    if not can_create_in_scope(db, user, scope):
        raise forbidden(f"无权在{SCOPE_LABELS[scope]}新建文档")

    if scope == SCOPE_COMPANY:
        return scope, None
    if scope == SCOPE_DEPARTMENT:
        user_depts = user_dept_ids(db, user.id)
        if not user_depts:
            raise bad_request("您未归属任何部门，无法在部门级新建文档")
        if dept_id is None:
            dept_id = primary_dept_id(db, user.id) or user_depts[0]
        if dept_id not in user_depts:
            raise forbidden("只能选择本人所属部门")
        return scope, dept_id
    return scope, None


SCOPE_SHARED = "shared"
SCOPE_ALL = "all"
SCOPE_RECYCLE = "recycle"

SCOPE_LABELS[SCOPE_SHARED] = "分享"
SCOPE_LABELS[SCOPE_ALL] = "所有"


def library_folders(db: Session, user: User) -> list[dict]:
    """前端文档库分级 Tab：我的 / 部门级 / 公司级 / 分享。"""
    folders = []
    for scope in LIBRARY_TAB_SCOPES:
        dept_for_perm = None
        if scope == SCOPE_DEPARTMENT:
            depts = user_dept_ids(db, user.id)
            dept_for_perm = depts[0] if depts else None
        folders.append(
            {
                "scope": scope,
                "label": SCOPE_LABELS[scope],
                "can_create": can_create_in_scope(db, user, scope),
                "can_edit": can_edit_in_scope(db, user, scope),
                "can_delete": can_delete_in_scope(db, user, scope),
                "can_manage_folders": can_manage_library_folders(
                    db, user, scope, dept_id=dept_for_perm
                ),
            }
        )
    folders.append(
        {
            "scope": SCOPE_SHARED,
            "label": SCOPE_LABELS[SCOPE_SHARED],
            "can_create": False,
            "can_edit": False,
            "can_delete": False,
            "can_manage_folders": False,
        }
    )
    return folders
