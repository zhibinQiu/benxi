from __future__ import annotations

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.services.documents.access_batch import filter_documents_for_list
from app.services.documents.acl import _subject_user_label
from app.services.documents.content import _is_compareable_version, _is_pdf_version
from app.services.documents.crud import is_version_uploaded


def _has_uploaded_version_exists():
    return exists(
        select(1).where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.file_size > 0,
        )
    )


def _document_title_or_filename_matches(keyword: str | None):
    """标题或当前/任意版本文件名包含关键词。"""
    kw = (keyword or "").strip()
    if not kw:
        return None
    pattern = f"%{kw}%"
    return or_(
        Document.title.ilike(pattern),
        exists(
            select(1).where(
                DocumentVersion.id == Document.current_version_id,
                DocumentVersion.file_name.ilike(pattern),
            )
        ),
        exists(
            select(1).where(
                DocumentVersion.document_id == Document.id,
                DocumentVersion.file_name.ilike(pattern),
            )
        ),
    )


def _user_share_meta(
    db: Session, user: User, document: Document
) -> dict[str, str | None]:
    """当前用户对该文档的显式用户级授权元数据。"""
    from datetime import datetime, timezone

    from app.core.permissions import level_order

    now = datetime.now(timezone.utc)
    perms = list(
        db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id,
                DocumentPermission.subject_type == "user",
                DocumentPermission.subject_id == user.id,
            )
        ).all()
    )
    best_level: str | None = None
    granted_by: uuid.UUID | None = None
    for perm in perms:
        if perm.expires_at and perm.expires_at < now:
            continue
        if best_level is None or level_order(perm.level) > level_order(best_level):
            best_level = perm.level
            granted_by = perm.granted_by
    granted_by_name: str | None = None
    if granted_by:
        granter = db.get(User, granted_by)
        if granter:
            from app.core.user_display import user_display_name

            granted_by_name = user_display_name(granter)
    return {"shared_level": best_level, "granted_by_name": granted_by_name}
def list_shared_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, dict[str, str | None]]], int]:
    """他人通过显式授权分享的文档（不含仅靠部门/公司默认可见的文档）。"""
    from app.core.document_scope import (
        _has_explicit_permission,
        can_read_document,
        readable_by_scope_default,
    )
    from app.core.permissions import PermissionLevel

    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.owner_id != user.id,
    )
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    stmt = stmt.where(_has_uploaded_version_exists())
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible: list[tuple[Document, dict[str, str | None]]] = []
    for doc in candidates:
        if not _has_explicit_permission(
            db, user, doc, PermissionLevel.visible.value
        ):
            continue
        if not can_read_document(db, user, doc):
            continue
        if readable_by_scope_default(db, user, doc):
            continue
        visible.append((doc, _user_share_meta(db, user, doc)))
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total
def filter_accessible_documents(
    db: Session,
    user: User,
    *,
    keyword: str | None = None,
    scope: str | None = None,
    min_permission_level: str | None = None,
    folder_id: uuid.UUID | None = None,
    uncategorized_only: bool = False,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> list[Document]:
    """返回当前用户满足权限要求的全部文档（不分页）。"""
    from app.core.document_scope import SCOPE_PERSONAL, VALID_SCOPES
    from app.core.permissions import user_dept_ids, user_is_superuser
    from app.models.document import DocumentStatus

    required = min_permission_level or PermissionLevel.visible.value
    is_super = user_is_superuser(db, user)
    if (
        owner_id is not None
        and owner_id != user.id
        and not is_super
    ):
        from app.core.exceptions import forbidden

        raise forbidden("无权查看他人个人文档库")
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if scope:
        if scope not in VALID_SCOPES:
            from app.core.exceptions import bad_request

            raise bad_request("无效的分级 scope")
        stmt = stmt.where(Document.scope == scope)
        if scope == SCOPE_PERSONAL:
            target_owner = owner_id if is_super and owner_id is not None else user.id
            if not is_super or owner_id is not None:
                stmt = stmt.where(Document.owner_id == target_owner)
        if scope in ("company", "department", "team"):
            if dept_id is not None:
                stmt = stmt.where(Document.dept_id == dept_id)
            elif not user_is_superuser(db, user):
                user_depts = user_dept_ids(db, user.id)
                if user_depts:
                    stmt = stmt.where(Document.dept_id.in_(user_depts))
                else:
                    stmt = stmt.where(Document.id.is_(None))
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    if uncategorized_only:
        stmt = stmt.where(Document.folder_id.is_(None))
    elif folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    stmt = stmt.where(_has_uploaded_version_exists())
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    return filter_documents_for_list(
        db,
        user,
        candidates,
        required_level=required,
        scope=scope,
    )


def list_accessible_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
    scope: str | None = None,
    min_permission_level: str | None = None,
    folder_id: uuid.UUID | None = None,
    uncategorized_only: bool = False,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> tuple[list[Document], int]:
    visible = filter_accessible_documents(
        db,
        user,
        keyword=keyword,
        scope=scope,
        min_permission_level=min_permission_level,
        folder_id=folder_id,
        uncategorized_only=uncategorized_only,
        dept_id=dept_id,
        owner_id=owner_id,
    )
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total
def list_all_visible_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    """跨分级汇总：当前用户具备「可见」及以上权限的全部文档（不做分级入库员过滤）。"""
    from app.models.document import DocumentStatus

    required = PermissionLevel.visible.value
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    stmt = stmt.where(_has_uploaded_version_exists())
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible = filter_documents_for_list(
        db,
        user,
        candidates,
        required_level=required,
    )
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total
def list_queryable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    """当前用户具备「可查询」及以上权限的全部启用文档（跨分级，含管理员可见范围）。"""
    from app.models.document import DocumentStatus

    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    stmt = stmt.where(_has_uploaded_version_exists())
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible = filter_documents_for_list(
        db,
        user,
        candidates,
        required_level=PermissionLevel.query.value,
    )
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total
def list_recycle_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    from sqlalchemy import and_

    stmt = select(Document).where(
        and_(
            Document.deleted_at.is_not(None),
            Document.deleted_by == user.id,
        )
    )
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    candidates = list(
        db.scalars(stmt.order_by(Document.deleted_at.desc())).all()
    )
    total = len(candidates)
    start = (page - 1) * page_size
    return candidates[start : start + page_size], total
def _list_documents_with_current_version(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    required_level: str,
    version_ok,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """未删除、已启用、当前版本已上传，且用户具备 required_level（通常为可查询）。"""
    from app.models.document import DocumentStatus

    cur_ver = DocumentVersion.__table__.alias("cur_ver")
    stmt = (
        select(Document)
        .join(cur_ver, Document.current_version_id == cur_ver.c.id)
        .where(
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.active.value,
            Document.current_version_id.is_not(None),
            cur_ver.c.file_size > 0,
        )
    )
    if keyword:
        title_filter = _document_title_or_filename_matches(keyword)
        if title_filter is not None:
            stmt = stmt.where(title_filter)
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    filtered = filter_documents_for_list(
        db,
        user,
        candidates,
        required_level=required_level,
    )
    rows: list[tuple[Document, DocumentVersion]] = []
    for doc in filtered:
        version = db.get(DocumentVersion, doc.current_version_id)
        if not version or not is_version_uploaded(version) or not version_ok(version):
            continue
        rows.append((doc, version))
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total
def list_translatable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """当前用户有「可查询」及以上权限、已上传 PDF 当前版本的文档。"""
    return _list_documents_with_current_version(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        required_level=PermissionLevel.query.value,
        version_ok=_is_pdf_version,
    )
def list_compareable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """当前用户有「可查询」及以上权限、可对比格式的当前版本文档。"""
    return _list_documents_with_current_version(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        required_level=PermissionLevel.query.value,
        version_ok=_is_compareable_version,
    )
