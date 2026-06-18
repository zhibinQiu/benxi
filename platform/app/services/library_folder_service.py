"""文档库知识库文件夹。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    ORG_SCOPES,
    SCOPE_COMPANY,
    SCOPE_PERSONAL,
    VALID_SCOPES,
    can_manage_library_folders,
    resolve_create_params,
)
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import user_is_superuser
from app.models.document import Document, DocumentLibraryFolder, DocumentStatus
from app.models.org import User

FOLDER_KIND_UNCATEGORIZED = "uncategorized"
FOLDER_KIND_SHARED = "shared"
FOLDER_KIND_WEB_FAVORITES = "web_favorites"
VIRTUAL_SHARED_ID = "__shared__"
VIRTUAL_UNCATEGORIZED_ID = "__uncategorized__"
WEB_FAVORITES_FOLDER_NAME = "网页收藏"

SYSTEM_FOLDER_HINTS = {
    FOLDER_KIND_UNCATEGORIZED: "尚未归入自定义文件夹的文档；不可删除或重命名。",
    FOLDER_KIND_SHARED: "其他用户通过显式授权分享给您的文档；不可删除或重命名。",
    FOLDER_KIND_WEB_FAVORITES: "通过网站收藏、公众号与 RSS 导入的文档会自动归入此文件夹。",
}


def _folder_visible_to_user(db: Session, user: User, folder: DocumentLibraryFolder) -> bool:
    if user_is_superuser(db, user):
        return True
    scope = folder.scope
    if scope == SCOPE_PERSONAL:
        return folder.owner_id == user.id
    if scope == SCOPE_COMPANY:
        return True
    if scope in ORG_SCOPES:
        if not folder.dept_id:
            return False
        from app.core.document_scope import user_can_access_org_unit

        return user_can_access_org_unit(db, user, folder.dept_id)
    return False


def _normalize_folder_scope(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    """规范化文件夹分级（列表、移动等，不校验新建权限）。"""
    if scope not in VALID_SCOPES:
        raise bad_request("无效的分级 scope")
    if scope in ORG_SCOPES:
        from app.core.document_scope import primary_dept_id, user_can_access_org_unit
        from app.core.permissions import user_dept_ids

        if user_is_superuser(db, user):
            if dept_id is None:
                raise bad_request("请选择组织节点")
            return scope, dept_id, None
        user_depts = user_dept_ids(db, user.id)
        if not user_depts:
            raise bad_request("您未归属任何部门")
        if dept_id is None:
            dept_id = primary_dept_id(db, user.id) or user_depts[0]
        if not user_can_access_org_unit(db, user, dept_id):
            raise forbidden("只能选择本人可访问的组织节点")
        return scope, dept_id, None
    if (
        owner_id is not None
        and owner_id != user.id
        and not user_is_superuser(db, user)
    ):
        raise forbidden("无权查看他人个人文档库")
    if user_is_superuser(db, user) and owner_id is not None:
        return SCOPE_PERSONAL, None, owner_id
    return SCOPE_PERSONAL, None, user.id


def _resolve_folder_params(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    norm_scope, norm_dept, owner_id = _normalize_folder_scope(
        db, user, scope=scope, dept_id=dept_id
    )
    norm_scope, norm_dept = resolve_create_params(
        db, user, scope=norm_scope, dept_id=norm_dept
    )
    owner_id = user.id if norm_scope == SCOPE_PERSONAL else None
    return norm_scope, norm_dept, owner_id


def _doc_count_filters(
    stmt,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
):
    from sqlalchemy import exists

    from app.models.document import DocumentVersion

    has_file = exists(
        select(1).where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.file_size > 0,
        )
    )
    stmt = stmt.where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        Document.scope == scope,
        has_file,
    )
    if scope == SCOPE_PERSONAL and owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
    if scope in ORG_SCOPES and dept_id:
        stmt = stmt.where(Document.dept_id == dept_id)
    return stmt


def _count_docs_in_folder(
    db: Session,
    *,
    scope: str,
    folder_id: uuid.UUID | None,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> int:
    stmt = select(func.count()).select_from(Document)
    stmt = _doc_count_filters(
        stmt, scope=scope, dept_id=dept_id, owner_id=owner_id
    )
    if folder_id is None:
        stmt = stmt.where(Document.folder_id.is_(None))
    else:
        stmt = stmt.where(Document.folder_id == folder_id)
    return int(db.scalar(stmt) or 0)


def _count_docs_grouped_by_folder(
    db: Session,
    *,
    scope: str,
    folder_ids: list[uuid.UUID],
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> dict[uuid.UUID | None, int]:
    """批量统计各文件夹（含未分类 folder_id=None）文档数。"""
    stmt = select(Document.folder_id, func.count()).select_from(Document)
    stmt = _doc_count_filters(
        stmt, scope=scope, dept_id=dept_id, owner_id=owner_id
    )
    if folder_ids:
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(
                Document.folder_id.is_(None),
                Document.folder_id.in_(folder_ids),
            )
        )
    stmt = stmt.group_by(Document.folder_id)
    return {row[0]: int(row[1]) for row in db.execute(stmt).all()}


def is_web_favorites_folder(folder: DocumentLibraryFolder | None) -> bool:
    if not folder:
        return False
    return (
        folder.scope == SCOPE_PERSONAL
        and (folder.name or "").strip() == WEB_FAVORITES_FOLDER_NAME
    )


def _backfill_subscription_imports_to_web_favorites(
    db: Session,
    *,
    folder: DocumentLibraryFolder,
    owner_id: uuid.UUID,
) -> None:
    from app.models.feed_subscription import FeedEntryImport
    from app.models.wechat_mp import WechatMpArticleImport

    if folder.owner_id != owner_id:
        return
    doc_ids: set[uuid.UUID] = set()
    for doc_id in db.scalars(
        select(FeedEntryImport.document_id).where(
            FeedEntryImport.user_id == owner_id
        )
    ):
        doc_ids.add(doc_id)
    for doc_id in db.scalars(
        select(WechatMpArticleImport.document_id).where(
            WechatMpArticleImport.user_id == owner_id
        )
    ):
        doc_ids.add(doc_id)
    if not doc_ids:
        return
    docs = list(
        db.scalars(
            select(Document).where(
                Document.id.in_(doc_ids),
                Document.owner_id == owner_id,
                Document.scope == SCOPE_PERSONAL,
                Document.folder_id.is_(None),
                Document.deleted_at.is_(None),
            )
        ).all()
    )
    if not docs:
        return
    for doc in docs:
        doc.folder_id = folder.id
    db.flush()


def ensure_web_favorites_folder(
    db: Session,
    user: User,
    owner_id: uuid.UUID,
) -> DocumentLibraryFolder:
    folder = db.scalar(
        select(DocumentLibraryFolder).where(
            DocumentLibraryFolder.scope == SCOPE_PERSONAL,
            DocumentLibraryFolder.owner_id == owner_id,
            DocumentLibraryFolder.name == WEB_FAVORITES_FOLDER_NAME,
        )
    )
    created = False
    if not folder:
        folder = DocumentLibraryFolder(
            name=WEB_FAVORITES_FOLDER_NAME,
            description=SYSTEM_FOLDER_HINTS[FOLDER_KIND_WEB_FAVORITES],
            scope=SCOPE_PERSONAL,
            dept_id=None,
            owner_id=owner_id,
            created_by=user.id,
        )
        db.add(folder)
        db.flush()
        created = True
    _backfill_subscription_imports_to_web_favorites(
        db, folder=folder, owner_id=owner_id
    )
    if created:
        db.commit()
        db.refresh(folder)
    return folder


def resolve_web_favorites_folder_id_for_user(
    db: Session, user: User
) -> uuid.UUID:
    folder = ensure_web_favorites_folder(db, user, owner_id=user.id)
    return folder.id


def assign_document_to_web_favorites_folder(
    db: Session, user: User, document_id: uuid.UUID
) -> None:
    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at is not None:
        return
    if doc.owner_id != user.id or doc.scope != SCOPE_PERSONAL:
        return
    if doc.folder_id is not None:
        return
    doc.folder_id = resolve_web_favorites_folder_id_for_user(db, user)
    db.flush()


def _build_kb_folders_payload(
    db: Session,
    user: User,
    *,
    norm_scope: str,
    norm_dept: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> dict:
    stmt = select(DocumentLibraryFolder).where(
        DocumentLibraryFolder.scope == norm_scope
    )
    if norm_scope == SCOPE_PERSONAL:
        target_owner = owner_id or user.id
        stmt = stmt.where(DocumentLibraryFolder.owner_id == target_owner)
    elif norm_scope in ORG_SCOPES:
        stmt = stmt.where(DocumentLibraryFolder.dept_id == norm_dept)

    rows = list(
        db.scalars(
            stmt.order_by(
                DocumentLibraryFolder.sort_order.asc(),
                DocumentLibraryFolder.created_at.asc(),
            )
        ).all()
    )

    can_manage = can_manage_library_folders(
        db, user, norm_scope, dept_id=norm_dept
    )
    web_favorites_folder = None
    if norm_scope == SCOPE_PERSONAL:
        target_owner = owner_id or user.id
        web_favorites_folder = ensure_web_favorites_folder(
            db, user, target_owner
        )

    visible_rows = [
        f
        for f in rows
        if _folder_visible_to_user(db, user, f)
        and not is_web_favorites_folder(f)
    ]
    folder_ids = [f.id for f in visible_rows]
    if web_favorites_folder is not None:
        folder_ids.append(web_favorites_folder.id)
    counts = _count_docs_grouped_by_folder(
        db,
        scope=norm_scope,
        folder_ids=folder_ids,
        dept_id=norm_dept,
        owner_id=owner_id if norm_scope == SCOPE_PERSONAL else None,
    )
    items: list[dict] = []

    uncategorized_count = counts.get(None, 0)
    items.append(
        {
            "id": None,
            "virtual_id": VIRTUAL_UNCATEGORIZED_ID,
            "name": "未分类",
            "description": SYSTEM_FOLDER_HINTS[FOLDER_KIND_UNCATEGORIZED],
            "scope": norm_scope,
            "dept_id": norm_dept,
            "kind": FOLDER_KIND_UNCATEGORIZED,
            "is_system": True,
            "system_hint": SYSTEM_FOLDER_HINTS[FOLDER_KIND_UNCATEGORIZED],
            "document_count": uncategorized_count,
            "can_manage": False,
        }
    )

    if norm_scope == SCOPE_PERSONAL:
        from app.services import document_service

        shared_total = document_service.list_shared_documents(
            db, user, page=1, page_size=1, keyword=None
        )[1]
        items.append(
            {
                "id": None,
                "virtual_id": VIRTUAL_SHARED_ID,
                "name": "分享",
                "description": SYSTEM_FOLDER_HINTS[FOLDER_KIND_SHARED],
                "scope": norm_scope,
                "dept_id": None,
                "kind": FOLDER_KIND_SHARED,
                "is_system": True,
                "system_hint": SYSTEM_FOLDER_HINTS[FOLDER_KIND_SHARED],
                "document_count": shared_total,
                "can_manage": False,
            }
        )
        if web_favorites_folder is not None:
            items.append(
                {
                    "id": web_favorites_folder.id,
                    "virtual_id": None,
                    "name": WEB_FAVORITES_FOLDER_NAME,
                    "description": SYSTEM_FOLDER_HINTS[FOLDER_KIND_WEB_FAVORITES],
                    "scope": norm_scope,
                    "dept_id": None,
                    "kind": FOLDER_KIND_WEB_FAVORITES,
                    "is_system": True,
                    "system_hint": SYSTEM_FOLDER_HINTS[FOLDER_KIND_WEB_FAVORITES],
                    "document_count": counts.get(web_favorites_folder.id, 0),
                    "can_manage": False,
                }
            )

    for folder in visible_rows:
        items.append(
            {
                "id": folder.id,
                "virtual_id": None,
                "name": folder.name,
                "description": folder.description or "",
                "scope": folder.scope,
                "dept_id": folder.dept_id,
                "kind": "normal",
                "is_system": False,
                "system_hint": None,
                "document_count": counts.get(folder.id, 0),
                "can_manage": can_manage,
            }
        )

    return {
        "scope": norm_scope,
        "dept_id": norm_dept,
        "can_manage_folders": can_manage,
        "items": items,
    }


def list_kb_folders(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> dict:
    norm_scope, norm_dept, norm_owner_id = _normalize_folder_scope(
        db, user, scope=scope, dept_id=dept_id, owner_id=owner_id
    )
    from app.config import get_settings
    from app.core.platform_cache import cache_get_or_set, kb_folders_cache_key

    dept_key = str(norm_dept) if norm_dept else None
    owner_key = str(norm_owner_id) if norm_owner_id else None
    cache_key = kb_folders_cache_key(str(user.id), norm_scope, dept_key, owner_key)
    ttl = max(5, int(get_settings().kb_folders_cache_ttl_sec))

    return cache_get_or_set(
        cache_key,
        lambda: _build_kb_folders_payload(
            db,
            user,
            norm_scope=norm_scope,
            norm_dept=norm_dept,
            owner_id=norm_owner_id,
        ),
        ttl=ttl,
    )


def create_kb_folder(
    db: Session,
    user: User,
    *,
    name: str,
    description: str = "",
    scope: str,
    dept_id: uuid.UUID | None = None,
) -> DocumentLibraryFolder:
    label = (name or "").strip()
    if not label:
        raise bad_request("文件夹名称不能为空")
    if label == WEB_FAVORITES_FOLDER_NAME:
        raise bad_request("该名称为系统保留文件夹，请换一个名称")
    if len(label) > 256:
        raise bad_request("文件夹名称过长")

    norm_scope, norm_dept, owner_id = _resolve_folder_params(
        db, user, scope=scope, dept_id=dept_id
    )
    if not can_manage_library_folders(
        db, user, norm_scope, dept_id=norm_dept
    ):
        raise forbidden("无权新建文件夹")

    exists = db.scalar(
        select(DocumentLibraryFolder.id).where(
            DocumentLibraryFolder.scope == norm_scope,
            DocumentLibraryFolder.name == label,
            DocumentLibraryFolder.dept_id.is_(None)
            if norm_dept is None
            else DocumentLibraryFolder.dept_id == norm_dept,
            DocumentLibraryFolder.owner_id.is_(None)
            if owner_id is None
            else DocumentLibraryFolder.owner_id == owner_id,
        )
    )
    if exists:
        raise bad_request("同名文件夹已存在")

    folder = DocumentLibraryFolder(
        name=label,
        description=(description or "").strip()[:2000],
        scope=norm_scope,
        dept_id=norm_dept,
        owner_id=owner_id,
        created_by=user.id,
    )
    db.add(folder)
    db.flush()
    return folder


def update_kb_folder(
    db: Session,
    user: User,
    folder_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
) -> DocumentLibraryFolder:
    folder = db.get(DocumentLibraryFolder, folder_id)
    if not folder:
        raise not_found("文件夹不存在")
    if is_web_favorites_folder(folder):
        raise forbidden("系统内置文件夹不可修改")
    if not _folder_visible_to_user(db, user, folder):
        raise not_found("文件夹不存在")
    if not can_manage_library_folders(
        db, user, folder.scope, dept_id=folder.dept_id
    ):
        raise forbidden("无权修改文件夹")

    if name is None and description is None:
        raise bad_request("请提供要修改的名称或介绍")
    if name is not None:
        label = name.strip()
        if not label:
            raise bad_request("文件夹名称不能为空")
        folder.name = label
    if description is not None:
        folder.description = description.strip()[:2000]
    db.flush()
    return folder


def delete_kb_folder(db: Session, user: User, folder_id: uuid.UUID) -> None:
    folder = db.get(DocumentLibraryFolder, folder_id)
    if not folder:
        raise not_found("文件夹不存在")
    if is_web_favorites_folder(folder):
        raise forbidden("系统内置文件夹不可删除")
    if not _folder_visible_to_user(db, user, folder):
        raise not_found("文件夹不存在")
    if not can_manage_library_folders(
        db, user, folder.scope, dept_id=folder.dept_id
    ):
        raise forbidden("无权删除文件夹")

    docs = list(
        db.scalars(
            select(Document).where(Document.folder_id == folder.id)
        ).all()
    )
    for doc in docs:
        doc.folder_id = None
    db.delete(folder)
    db.flush()


def resolve_document_folder_id(
    db: Session,
    user: User,
    *,
    scope: str,
    folder_id: uuid.UUID | None,
    dept_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """校验文档所属文件夹与分级一致。"""
    if folder_id is None:
        return None
    folder = db.get(DocumentLibraryFolder, folder_id)
    if not folder:
        raise bad_request("文件夹不存在")
    if not _folder_visible_to_user(db, user, folder):
        raise forbidden("无权使用该文件夹")
    norm_scope, norm_dept, owner_id = _normalize_folder_scope(
        db, user, scope=scope, dept_id=dept_id
    )
    if folder.scope != norm_scope:
        raise bad_request("文件夹与文档分级不一致")
    if norm_scope in ORG_SCOPES and folder.dept_id != norm_dept:
        raise bad_request("文件夹与所选组织单元不一致")
    if (
        norm_scope == SCOPE_PERSONAL
        and folder.owner_id != user.id
        and not user_is_superuser(db, user)
    ):
        raise forbidden("无权使用该文件夹")
    return folder.id
