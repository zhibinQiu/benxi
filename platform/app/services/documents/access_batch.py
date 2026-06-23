"""文档列表批量权限上下文：避免逐条查 permissions / denials。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    ORG_SCOPES,
    SCOPE_PERSONAL,
    owner_qualifies_for_scope_list,
    scope_perm,
)
from app.core.permissions import (
    PermissionLevel,
    level_order,
    level_satisfies,
    normalize_permission_level,
    user_dept_ids,
    user_has_permission,
    user_is_superuser,
    user_role_ids,
)
from app.models.document import Document, DocumentPermission, DocumentStatus
from app.models.document_workflow import DocumentAccessDenial
from app.models.org import User


@dataclass
class DocumentListAccessContext:
    db: Session
    user: User
    is_super: bool
    user_id: uuid.UUID
    has_doc_read: bool
    denied_ids: frozenset[uuid.UUID]
    explicit_levels: dict[uuid.UUID, str]
    org_access: dict[uuid.UUID, bool] = field(default_factory=dict)
    scope_edit: dict[str, bool] = field(default_factory=dict)


def _best_explicit_levels(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not doc_ids:
        return {}
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
    now = datetime.now(timezone.utc)
    best: dict[uuid.UUID, str] = {}
    for perm in db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id.in_(doc_ids),
            or_(*conditions),
        )
    ).all():
        if perm.expires_at and perm.expires_at < now:
            continue
        cur = best.get(perm.document_id)
        if cur is None or level_order(perm.level) > level_order(cur):
            best[perm.document_id] = perm.level
    return best


def _batch_denied_ids(
    db: Session, user_id: uuid.UUID, doc_ids: list[uuid.UUID]
) -> frozenset[uuid.UUID]:
    if not doc_ids:
        return frozenset()
    rows = db.scalars(
        select(DocumentAccessDenial.document_id).where(
            DocumentAccessDenial.user_id == user_id,
            DocumentAccessDenial.document_id.in_(doc_ids),
        )
    ).all()
    return frozenset(rows)


def build_list_access_context(
    db: Session, user: User, documents: list[Document]
) -> DocumentListAccessContext:
    from app.core.document_scope import user_can_access_org_unit

    doc_ids = [d.id for d in documents]
    is_super = user_is_superuser(db, user)
    ctx = DocumentListAccessContext(
        db=db,
        user=user,
        is_super=is_super,
        user_id=user.id,
        has_doc_read=user_has_permission(db, user, "doc.read"),
        denied_ids=_batch_denied_ids(db, user.id, doc_ids),
        explicit_levels=_best_explicit_levels(db, user, doc_ids),
    )
    if is_super:
        return ctx
    for doc in documents:
        dept_id = doc.dept_id
        if dept_id and dept_id not in ctx.org_access:
            ctx.org_access[dept_id] = user_can_access_org_unit(db, user, dept_id)
    return ctx


def _explicit_satisfies(
    ctx: DocumentListAccessContext, doc_id: uuid.UUID, level: str
) -> bool:
    got = ctx.explicit_levels.get(doc_id)
    return bool(got and level_satisfies(got, normalize_permission_level(level)))


def _scope_readable_default(ctx: DocumentListAccessContext, document: Document) -> bool:
    if document.id in ctx.denied_ids:
        return False
    scope = document.scope or SCOPE_PERSONAL
    if scope == SCOPE_PERSONAL:
        return document.owner_id == ctx.user_id
    if scope in ORG_SCOPES:
        if document.owner_id == ctx.user_id:
            return True
        return bool(
            document.dept_id
            and ctx.has_doc_read
            and ctx.org_access.get(document.dept_id, False)
        )
    return False


def _can_read(ctx: DocumentListAccessContext, document: Document) -> bool:
    if document.deleted_at is not None:
        return False
    if ctx.is_super:
        return True
    if document.status == DocumentStatus.disabled.value and not _can_modify(
        ctx, document
    ):
        return False
    if _explicit_satisfies(ctx, document.id, PermissionLevel.visible.value):
        return True
    if document.id in ctx.denied_ids:
        return False
    scope = document.scope or SCOPE_PERSONAL
    if scope == SCOPE_PERSONAL:
        return document.owner_id == ctx.user_id
    if scope in ORG_SCOPES:
        if document.owner_id == ctx.user_id:
            return True
        if not document.dept_id:
            return False
        if not ctx.has_doc_read:
            return False
        return ctx.org_access.get(document.dept_id, False)
    return False


def _scope_edit_allowed(ctx: DocumentListAccessContext, scope: str) -> bool:
    if scope not in ctx.scope_edit:
        ctx.scope_edit[scope] = user_has_permission(
            ctx.db, ctx.user, scope_perm(scope, "edit")
        )
    return ctx.scope_edit[scope]


def _can_modify(ctx: DocumentListAccessContext, document: Document) -> bool:
    if document.deleted_at is not None:
        return False
    if document.id in ctx.denied_ids:
        return False
    if ctx.is_super:
        return True
    if document.owner_id == ctx.user_id:
        return True
    if _explicit_satisfies(ctx, document.id, PermissionLevel.modify.value):
        return True
    if _scope_readable_default(ctx, document):
        return True
    scope = document.scope or SCOPE_PERSONAL
    if scope in ORG_SCOPES:
        return _scope_edit_allowed(ctx, scope)
    return False


def _can_query(ctx: DocumentListAccessContext, document: Document) -> bool:
    if not _can_read(ctx, document):
        return False
    if ctx.is_super:
        return True
    if document.owner_id == ctx.user_id:
        return True
    if _explicit_satisfies(ctx, document.id, PermissionLevel.query.value):
        return True
    return _can_modify(ctx, document)


def can_access_document_fast(
    ctx: DocumentListAccessContext,
    document: Document,
    required_level: str,
) -> bool:
    level = normalize_permission_level(required_level)
    if level == PermissionLevel.visible.value:
        return _can_read(ctx, document)
    if level == PermissionLevel.query.value:
        return _can_query(ctx, document)
    if level == PermissionLevel.modify.value:
        return _can_modify(ctx, document)
    return False


def filter_documents_for_list(
    db: Session,
    user: User,
    documents: list[Document],
    *,
    required_level: str,
    scope: str | None = None,
) -> list[Document]:
    """批量权限过滤，替代逐条 can_access_document + N+1。"""
    if not documents:
        return []
    ctx = build_list_access_context(db, user, documents)
    is_super = ctx.is_super
    visible: list[Document] = []
    for doc in documents:
        if not can_access_document_fast(ctx, doc, required_level):
            continue
        doc_scope = doc.scope or SCOPE_PERSONAL
        if scope == SCOPE_PERSONAL and doc.owner_id != user.id and not is_super:
            continue
        if (
            not is_super
            and doc_scope in ORG_SCOPES
            and not owner_qualifies_for_scope_list(db, doc)
        ):
            continue
        visible.append(doc)
    return visible
