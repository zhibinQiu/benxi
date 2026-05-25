"""分级知识库：公司/部门/个人单库共享，平台 ACL → KnowFlow RBAC 授权。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    _document_scope,
    can_delete_document,
    can_edit_document,
    can_edit_in_scope,
    can_query_document,
    can_read_document,
)
from app.core.permissions import PermissionLevel, user_dept_ids, user_has_permission, user_is_superuser
from app.integrations.ragflow_kb_acl import grant_kb_user_permission, revoke_kb_user_permission
from app.models.document import Document
from app.models.org import User, UserDepartment
from app.models.ragflow_link import RagflowAccountLink
from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
    SCOPE_PERSONAL as REG_PERSONAL,
    RagflowScopeDataset,
)
from app.services.ragflow_identity_service import get_or_create_link
from app.services.ragflow_naming import (
    dataset_name_for_company,
    dataset_name_for_dept,
    dataset_name_for_personal,
)

logger = logging.getLogger(__name__)

COMPANY_SCOPE_KEY = "global"


def scope_key_for_document(document: Document) -> str:
    scope = _document_scope(document)
    if scope == SCOPE_COMPANY:
        return COMPANY_SCOPE_KEY
    if scope == SCOPE_DEPARTMENT:
        if document.dept_id:
            return str(document.dept_id)
        return str(document.owner_id)
    return str(document.owner_id)


def _get_registry(
    db: Session, scope: str, scope_key: str
) -> RagflowScopeDataset | None:
    return db.scalar(
        select(RagflowScopeDataset).where(
            RagflowScopeDataset.scope == scope,
            RagflowScopeDataset.scope_key == scope_key,
        )
    )


def _can_create_scope_dataset(db: Session, user: User, scope: str) -> bool:
    if user_is_superuser(db, user):
        return True
    if scope == SCOPE_PERSONAL:
        return True
    return can_edit_in_scope(db, user, scope)


def ensure_scope_dataset(
    db: Session,
    actor: User,
    scope: str,
    scope_key: str,
    kf,
) -> str | None:
    """确保分级知识库存在（全局唯一），返回 ragflow dataset id。"""
    reg_scope = {
        SCOPE_COMPANY: REG_COMPANY,
        SCOPE_DEPARTMENT: REG_DEPARTMENT,
        SCOPE_PERSONAL: REG_PERSONAL,
    }.get(scope, REG_PERSONAL)

    existing = _get_registry(db, reg_scope, scope_key)
    if existing:
        return existing.ragflow_dataset_id

    if not _can_create_scope_dataset(db, actor, scope):
        logger.info("用户 %s 无权创建 %s 知识库", actor.username, scope)
        return None

    if scope == SCOPE_COMPANY:
        name = dataset_name_for_company()
    elif scope == SCOPE_DEPARTMENT:
        name = dataset_name_for_dept(uuid.UUID(scope_key))
    else:
        name = dataset_name_for_personal(uuid.UUID(scope_key))
    try:
        ds_id = kf._rag.ensure_dataset(name)
    except Exception as e:
        logger.warning("创建知识库 %s 失败: %s", name, e)
        return None

    link = get_or_create_link(db, actor)
    reg = RagflowScopeDataset(
        scope=reg_scope,
        scope_key=scope_key,
        ragflow_dataset_id=ds_id,
        owner_ragflow_user_id=link.ragflow_user_id,
    )
    db.add(reg)
    db.flush()
    return ds_id


def resolve_dataset_for_document(db: Session, actor: User, document: Document, kf) -> str | None:
    scope = _document_scope(document)
    key = scope_key_for_document(document)
    return ensure_scope_dataset(db, actor, scope, key, kf)


def _user_has_queryable_doc_in_scope(
    db: Session,
    user: User,
    scope: str,
    *,
    dept_id: uuid.UUID | None = None,
) -> bool:
    """用户在某分级下是否至少有一份可查询的启用文档。"""
    from app.models.document import DocumentStatus

    stmt = select(Document.id).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        Document.scope == scope,
    )
    if scope == SCOPE_DEPARTMENT and dept_id:
        stmt = stmt.where(Document.dept_id == dept_id)
    for doc_id in db.scalars(stmt.limit(300)):
        doc = db.get(Document, doc_id)
        if doc and can_query_document(db, user, doc):
            return True
    return False


def kb_level_for_user_on_document(db: Session, user: User, document: Document) -> str | None:
    """平台文档权限 → KnowFlow 知识库权限（仅「可查询」及以上可检索）。"""
    if not can_query_document(db, user, document):
        return None
    if can_delete_document(db, user, document):
        return "admin"
    if can_edit_document(db, user, document):
        return "write"
    return "read"


def _ragflow_user_id(db: Session, platform_user_id: uuid.UUID) -> str | None:
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == platform_user_id
        )
    )
    return (link.ragflow_user_id or "").strip() or None if link else None


def sync_document_kb_grants(db: Session, document: Document) -> int:
    """按平台文档 ACL 同步该文档所在知识库的 KnowFlow 授权（不复制文档）。"""
    from app.models.ragflow_document_link import RagflowDocumentLink

    link = db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document.id
        )
    )
    if not link or not link.dataset_id:
        return 0

    scope = _document_scope(document)
    granted = 0
    if scope == SCOPE_PERSONAL:
        candidates = [document.owner_id]
        from app.models.document import DocumentPermission

        perms = db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id,
                DocumentPermission.subject_type == "user",
            )
        ).all()
        for p in perms:
            candidates.append(p.subject_id)
        seen: set[uuid.UUID] = set()
        for uid in candidates:
            if uid in seen:
                continue
            seen.add(uid)
            user = db.get(User, uid)
            if not user:
                continue
            level = kb_level_for_user_on_document(db, user, document)
            rid = _ragflow_user_id(db, uid)
            if level and rid and grant_kb_user_permission(link.dataset_id, rid, level):
                granted += 1
        return granted

    if scope == SCOPE_DEPARTMENT and document.dept_id:
        return _sync_dept_kb_grants(db, document.dept_id, link.dataset_id)

    if scope == SCOPE_COMPANY:
        return _sync_company_kb_grants(db, link.dataset_id)

    return granted


def _sync_dept_kb_grants(db: Session, dept_id: uuid.UUID, dataset_id: str) -> int:
    """部门库授权：仅授予当前部门成员（user_departments）。"""
    granted = 0
    rows = db.scalars(
        select(UserDepartment.user_id).where(UserDepartment.dept_id == dept_id)
    ).all()
    for uid in rows:
        user = db.get(User, uid)
        if not user or user.status != "active":
            continue
        level = _dept_kb_level(db, user, dept_id)
        if not level:
            continue
        rid = _ragflow_user_id(db, uid)
        if rid and grant_kb_user_permission(dataset_id, rid, level):
            granted += 1
    return granted


def _sync_company_kb_grants(db: Session, dataset_id: str) -> int:
    granted = 0
    users = db.scalars(select(User).where(User.status == "active")).all()
    for user in users:
        level = _company_kb_level(db, user)
        if not level:
            continue
        rid = _ragflow_user_id(db, user.id)
        if rid and grant_kb_user_permission(dataset_id, rid, level):
            granted += 1
    return granted


def _dept_kb_level(db: Session, user: User, dept_id: uuid.UUID) -> str | None:
    if can_edit_in_scope(db, user, SCOPE_DEPARTMENT):
        return "write"
    if _user_has_queryable_doc_in_scope(db, user, SCOPE_DEPARTMENT, dept_id=dept_id):
        return "read"
    return None


def _company_kb_level(db: Session, user: User) -> str | None:
    if user_is_superuser(db, user):
        return "admin"
    if can_edit_in_scope(db, user, SCOPE_COMPANY):
        return "write"
    if _user_has_queryable_doc_in_scope(db, user, SCOPE_COMPANY):
        return "read"
    return None


def revoke_all_dept_kb_grants(db: Session, user: User) -> int:
    """删除用户或清空部门时：撤销其全部部门知识库授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0
    revoked = 0
    for reg in db.scalars(
        select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_DEPARTMENT)
    ).all():
        if revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1
    return revoked


def revoke_stale_dept_kb_grants(db: Session, user: User) -> int:
    """回收已不在所属部门的 KnowFlow 部门库授权（仅保留 user_dept_ids）。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0
    allowed = {str(d) for d in user_dept_ids(db, user.id)}
    revoked = 0
    for reg in db.scalars(select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_DEPARTMENT)).all():
        if reg.scope_key in allowed:
            continue
        if revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1
    return revoked


def reconcile_dept_membership_kb(
    db: Session,
    user: User,
    *,
    previous_dept_ids: list[uuid.UUID] | None = None,
) -> int:
    """部门成员变动：撤销离开部门的库权限，并刷新当前所属部门授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0

    current = {str(d) for d in user_dept_ids(db, user.id)}
    removed = set()
    if previous_dept_ids is not None:
        removed = {str(d) for d in previous_dept_ids} - current

    revoked = 0
    for dept_key in removed:
        reg = _get_registry(db, REG_DEPARTMENT, dept_key)
        if reg and revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1

    granted = 0
    for dept_id in user_dept_ids(db, user.id):
        reg = _get_registry(db, REG_DEPARTMENT, str(dept_id))
        if not reg:
            continue
        level = _dept_kb_level(db, user, dept_id)
        if level and grant_kb_user_permission(
            reg.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            granted += 1
    return revoked + granted


def sync_user_kb_grants(db: Session, user: User) -> int:
    """登录/进入知识问答：仅对本人所属部门/有公司权限的知识库授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0

    count = revoke_stale_dept_kb_grants(db, user)

    personal = _get_registry(db, REG_PERSONAL, str(user.id))
    if personal and grant_kb_user_permission(
        personal.ragflow_dataset_id, link.ragflow_user_id, "admin"
    ):
        count += 1

    for dept_id in user_dept_ids(db, user.id):
        reg = _get_registry(db, REG_DEPARTMENT, str(dept_id))
        if not reg:
            continue
        level = _dept_kb_level(db, user, dept_id)
        if level and grant_kb_user_permission(
            reg.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            count += 1

    company = _get_registry(db, REG_COMPANY, COMPANY_SCOPE_KEY)
    if company:
        level = _company_kb_level(db, user)
        if level and grant_kb_user_permission(
            company.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            count += 1

    return count


def ensure_user_scope_datasets(db: Session, user: User, kf) -> None:
    """预创建用户相关的分级知识库（个人 + 所属部门 + 公司）。"""
    ensure_scope_dataset(db, user, SCOPE_PERSONAL, str(user.id), kf)
    for dept_id in user_dept_ids(db, user.id):
        ensure_scope_dataset(db, user, SCOPE_DEPARTMENT, str(dept_id), kf)
    if user_has_permission(db, user, "doc.read") or user_is_superuser(db, user):
        ensure_scope_dataset(db, user, SCOPE_COMPANY, COMPANY_SCOPE_KEY, kf)
