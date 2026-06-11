"""文档库分级（公司 / 部门 / 小组 / 个人）与分级权限。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import (
    PermissionLevel,
    level_satisfies,
    normalize_permission_level,
    user_dept_ids,
    user_has_permission,
    user_is_superuser,
)
from app.models.document import Document, DocumentPermission, DocumentStatus
from app.models.org import Department, User

DocumentScope = str

SCOPE_COMPANY = "company"
SCOPE_DEPARTMENT = "department"
SCOPE_TEAM = "team"
SCOPE_PERSONAL = "personal"

VALID_SCOPES = (SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_TEAM, SCOPE_PERSONAL)
# 文档库 Tab：个人级 → 小组级 → 部门级 → 公司级（分享另列）
LIBRARY_TAB_SCOPES = (
    SCOPE_PERSONAL,
    SCOPE_TEAM,
    SCOPE_DEPARTMENT,
    SCOPE_COMPANY,
)

SCOPE_LABELS = {
    SCOPE_COMPANY: "公司级",
    SCOPE_DEPARTMENT: "部门级",
    SCOPE_TEAM: "小组级",
    SCOPE_PERSONAL: "个人级",
}

# 绑定组织节点的分级（根=公司，二级=部门，三级=小组）
ORG_SCOPES = (SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_TEAM)
DEPT_SCOPES = ORG_SCOPES


def content_subscription_import_scope() -> str:
    """公众号 / RSS / 网站资讯导入文档库时固定为「个人级」分级。"""
    return SCOPE_PERSONAL

_SCOPE_PERM_PREFIX = {
    SCOPE_COMPANY: "doc.company",
    SCOPE_DEPARTMENT: "doc.dept",
    SCOPE_TEAM: "doc.team",
    SCOPE_PERSONAL: "doc.personal",
}


def department_depth(db: Session, dept_id: uuid.UUID) -> int:
    """组织树深度：根节点=0（公司级），子节点依次 +1。"""
    depth = 0
    current = db.get(Department, dept_id)
    while current and current.parent_id:
        depth += 1
        current = db.get(Department, current.parent_id)
    return depth


def scope_for_department_depth(depth: int) -> str:
    if depth == 0:
        return SCOPE_COMPANY
    if depth == 1:
        return SCOPE_DEPARTMENT
    if depth == 2:
        return SCOPE_TEAM
    return SCOPE_PERSONAL


def scope_for_department(db: Session, dept_id: uuid.UUID) -> str:
    return scope_for_department_depth(department_depth(db, dept_id))


def department_root_id(db: Session, dept_id: uuid.UUID) -> uuid.UUID:
    current = db.get(Department, dept_id)
    if not current:
        return dept_id
    while current.parent_id:
        parent = db.get(Department, current.parent_id)
        if not parent:
            break
        current = parent
    return current.id


def is_ancestor_department(
    db: Session, ancestor_id: uuid.UUID, descendant_id: uuid.UUID
) -> bool:
    current = db.get(Department, descendant_id)
    while current and current.parent_id:
        if current.parent_id == ancestor_id:
            return True
        current = db.get(Department, current.parent_id)
    return descendant_id == ancestor_id


def user_can_access_org_unit(db: Session, user: User, dept_id: uuid.UUID) -> bool:
    """用户属于该节点或其下级组织。"""
    if user_is_superuser(db, user):
        return True
    for did in user_dept_ids(db, user.id):
        if did == dept_id or is_ancestor_department(db, dept_id, did):
            return True
    return False


def validate_dept_for_scope(db: Session, scope: str, dept_id: uuid.UUID) -> None:
    from app.core.exceptions import bad_request

    expected = scope_for_department(db, dept_id)
    if scope != expected:
        raise bad_request(
            f"该组织节点对应「{SCOPE_LABELS[expected]}」，与所选「{SCOPE_LABELS[scope]}」不一致"
        )


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
    """知识库文件夹新建/删除：具备对应分级 create 权限即可。"""
    if scope not in VALID_SCOPES:
        return False
    if user_is_superuser(db, user):
        return True
    if not can_create_in_scope(db, user, scope):
        return False
    if scope in ORG_SCOPES and dept_id is not None:
        return user_can_access_org_unit(db, user, dept_id)
    return True


def _document_scope(db: Session, doc: Document) -> str:
    s = (getattr(doc, "scope", None) or "").strip()
    if s in VALID_SCOPES:
        return s
    if doc.dept_id:
        return scope_for_department(db, doc.dept_id)
    return SCOPE_PERSONAL


def has_explicit_user_query_share(
    db: Session, user: User, document: Document
) -> bool:
    """他人对当前用户的显式用户级分享，且档位为可查询及以上。"""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.permissions import PermissionLevel, level_satisfies

    now = datetime.now(timezone.utc)
    perms = db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == "user",
            DocumentPermission.subject_id == user.id,
        )
    ).all()
    for perm in perms:
        if perm.expires_at and perm.expires_at < now:
            continue
        if level_satisfies(perm.level, PermissionLevel.query.value):
            return True
    return False


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


def _scope_default_grants_modify(
    db: Session, user: User, document: Document
) -> bool:
    """组织分级默认：团队成员默认可修改（上传/分享/重建索引/删除）。"""
    return readable_by_scope_default(db, user, document)


def can_modify_document(db: Session, user: User, document: Document) -> bool:
    """可修改：上传、分享、重建索引、删除、管理状态等。"""
    if document.deleted_at is not None:
        return False
    if is_access_denied(db, user, document):
        return False
    if user_is_superuser(db, user):
        return True
    if document.owner_id == user.id:
        return True
    if _has_explicit_permission(db, user, document, PermissionLevel.modify.value):
        return True
    if _scope_default_grants_modify(db, user, document):
        return True
    scope = _document_scope(db, document)
    if scope in (SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_TEAM):
        return can_edit_in_scope(db, user, scope)
    return False


def can_manage_document(db: Session, user: User, document: Document) -> bool:
    """兼容：等同 can_modify_document。"""
    return can_modify_document(db, user, document)


def can_grant_document_permissions(db: Session, user: User, document: Document) -> bool:
    """显式文档授权：创建人、系统管理员、或被授予可修改的用户。"""
    if document.deleted_at is not None:
        return False
    if user_is_superuser(db, user):
        return True
    if document.owner_id == user.id:
        return True
    return _has_explicit_permission(db, user, document, PermissionLevel.modify.value)


def can_manage_document_denials(db: Session, user: User, document: Document) -> bool:
    """禁止访问：仅文档创建人与系统管理员。"""
    if document.deleted_at is not None:
        return False
    return user_is_superuser(db, user) or document.owner_id == user.id


def can_manage_document_acl(db: Session, user: User, document: Document) -> bool:
    """兼容：任一类文档 ACL 管理权限。"""
    return can_grant_document_permissions(db, user, document) or can_manage_document_denials(
        db, user, document
    )


def owner_qualifies_for_scope_list(db: Session, document: Document) -> bool:
    """公司/部门库列表：展示已发布到该分级的文档（与上传者角色无关）。"""
    scope = _document_scope(db, document)
    if scope in ORG_SCOPES:
        return document.dept_id is not None
    return True


def can_read_document(db: Session, user: User, document: Document) -> bool:
    if document.deleted_at is not None:
        return False
    if user_is_superuser(db, user):
        return True

    if document.status == DocumentStatus.disabled.value:
        if not can_modify_document(db, user, document):
            return False

    scope = _document_scope(db, document)
    if _has_explicit_permission(db, user, document, PermissionLevel.visible.value):
        return True

    if is_access_denied(db, user, document):
        return False

    if scope == SCOPE_PERSONAL:
        return document.owner_id == user.id

    if scope in ORG_SCOPES:
        if document.owner_id == user.id:
            return True
        if not document.dept_id:
            return False
        if not user_has_permission(db, user, "doc.read"):
            return False
        return user_can_access_org_unit(db, user, document.dept_id)

    return False


def readable_by_scope_default(db: Session, user: User, document: Document) -> bool:
    """不依赖显式授权时，是否因分级归属而默认可读（用于「分享」列表去重）。"""
    if document.deleted_at is not None:
        return False
    if is_access_denied(db, user, document):
        return False

    scope = _document_scope(db, document)
    if scope == SCOPE_PERSONAL:
        return document.owner_id == user.id
    if scope in ORG_SCOPES:
        if document.owner_id == user.id:
            return True
        return bool(
            document.dept_id
            and user_has_permission(db, user, "doc.read")
            and user_can_access_org_unit(db, user, document.dept_id)
        )
    return False


def can_query_document(db: Session, user: User, document: Document) -> bool:
    """可在知识问答 / KnowFlow 中检索该文档。"""
    if not can_read_document(db, user, document):
        return False
    if user_is_superuser(db, user):
        return True
    if document.owner_id == user.id:
        return True
    if _has_explicit_permission(db, user, document, PermissionLevel.query.value):
        return True
    if can_modify_document(db, user, document):
        return True
    return False


def can_edit_document(db: Session, user: User, document: Document) -> bool:
    """兼容旧名：等同 can_modify_document。"""
    return can_modify_document(db, user, document)


def can_use_document(db: Session, user: User, document: Document) -> bool:
    """兼容旧名：等同 can_modify_document。"""
    return can_modify_document(db, user, document)


def can_delete_document(db: Session, user: User, document: Document) -> bool:
    """删除文档（含知识库索引）：等同 can_modify_document。"""
    return can_modify_document(db, user, document)


def can_restore_document(db: Session, user: User, document: Document) -> bool:
    """从个人回收站恢复。"""
    if document.deleted_at is None:
        return False
    if document.deleted_by and document.deleted_by == user.id:
        return True
    return can_manage_document(db, user, document)


def effective_permission_level(db: Session, user: User, document: Document) -> str | None:
    """当前用户对该文档的综合能力档位（用于界面展示）。"""
    if can_modify_document(db, user, document):
        return PermissionLevel.modify.value
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
    if level == PermissionLevel.modify.value:
        return can_modify_document(db, user, document)
    return False


def primary_dept_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    from app.core.user_department import user_department_id

    return user_department_id(db, user_id)


def resolve_create_params(
    db: Session, user: User, *, scope: str, dept_id: uuid.UUID | None
) -> tuple[str, uuid.UUID | None]:
    """校验新建权限并返回规范化 (scope, dept_id)。"""
    from app.core.exceptions import bad_request, forbidden

    if scope not in VALID_SCOPES:
        raise bad_request("无效的分级 scope")
    if not can_create_in_scope(db, user, scope):
        raise forbidden(f"无权在{SCOPE_LABELS[scope]}新建文档")

    if scope in ORG_SCOPES:
        label = SCOPE_LABELS[scope]
        if dept_id is None:
            raise bad_request(f"请选择{label}所属组织")
        validate_dept_for_scope(db, scope, dept_id)
        if user_is_superuser(db, user):
            return scope, dept_id
        user_depts = user_dept_ids(db, user.id)
        if not user_depts:
            raise bad_request(f"您未归属任何部门，无法在{label}新建文档")
        if not user_can_access_org_unit(db, user, dept_id):
            raise forbidden("只能选择本人可访问的组织节点")
        return scope, dept_id
    return scope, None


SCOPE_SHARED = "shared"
SCOPE_ALL = "all"
SCOPE_RECYCLE = "recycle"

SCOPE_LABELS[SCOPE_SHARED] = "分享"
SCOPE_LABELS[SCOPE_ALL] = "所有"


def _all_departments_for_user(db: Session, user: User) -> list[dict]:
    if user_is_superuser(db, user):
        rows = db.scalars(select(Department).order_by(Department.name)).all()
        return [{"id": d.id, "name": d.name} for d in rows]
    out: list[dict] = []
    for did in user_dept_ids(db, user.id):
        d = db.get(Department, did)
        if d:
            out.append({"id": d.id, "name": d.name})
    out.sort(key=lambda x: x["name"])
    return out


def _library_org_units_for_user(
    db: Session, user: User, *, depth: int
) -> list[dict]:
    if user_is_superuser(db, user):
        rows = db.scalars(select(Department).order_by(Department.name)).all()
        return [
            {"id": d.id, "name": d.name}
            for d in rows
            if department_depth(db, d.id) == depth
        ]
    seen: set[uuid.UUID] = set()
    out: list[dict] = []
    for did in user_dept_ids(db, user.id):
        d = db.get(Department, did)
        if not d or department_depth(db, d.id) != depth:
            continue
        if d.id in seen:
            continue
        seen.add(d.id)
        out.append({"id": d.id, "name": d.name})
    out.sort(key=lambda x: x["name"])
    return out


def library_companies_for_user(db: Session, user: User) -> list[dict]:
    """公司级 Tab：组织树根节点（depth=0）。"""
    if user_is_superuser(db, user):
        return _library_org_units_for_user(db, user, depth=0)
    seen: set[uuid.UUID] = set()
    out: list[dict] = []
    for did in user_dept_ids(db, user.id):
        root_id = department_root_id(db, did)
        if root_id in seen:
            continue
        seen.add(root_id)
        root = db.get(Department, root_id)
        if root:
            out.append({"id": root.id, "name": root.name})
    out.sort(key=lambda x: x["name"])
    return out


def library_departments_for_user(db: Session, user: User) -> list[dict]:
    """部门级 Tab：二级节点（depth=1）。"""
    return _library_org_units_for_user(db, user, depth=1)


def library_teams_for_user(db: Session, user: User) -> list[dict]:
    """小组级 Tab：三级节点（depth=2）。"""
    return _library_org_units_for_user(db, user, depth=2)


def library_folders(db: Session, user: User) -> list[dict]:
    """前端文档库分级 Tab：个人级 / 小组级 / 部门级 / 公司级 / 分享。"""
    folders = []
    for scope in LIBRARY_TAB_SCOPES:
        dept_for_perm = None
        if scope in ORG_SCOPES:
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
