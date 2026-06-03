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
from app.core.permissions import user_is_superuser
from app.core.exceptions import bad_request, forbidden, not_found
from app.models.document import Document, DocumentLibraryFolder
from app.models.document import DocumentStatus
from app.models.org import User

FOLDER_KIND_UNCATEGORIZED = "uncategorized"
FOLDER_KIND_SHARED = "shared"
VIRTUAL_SHARED_ID = "__shared__"
VIRTUAL_UNCATEGORIZED_ID = "__uncategorized__"

SYSTEM_FOLDER_HINTS = {
    FOLDER_KIND_UNCATEGORIZED: "尚未归入自定义文件夹的文档；不可删除或重命名。",
    FOLDER_KIND_SHARED: "其他用户通过显式授权分享给您的文档；不可删除或重命名。",
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


def _count_docs_in_folder(
    db: Session,
    *,
    scope: str,
    folder_id: uuid.UUID | None,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> int:
    from app.models.document import DocumentVersion
    from sqlalchemy import exists

    has_file = exists(
        select(1).where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.file_size > 0,
        )
    )
    stmt = select(func.count()).select_from(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        Document.scope == scope,
        has_file,
    )
    if folder_id is None:
        stmt = stmt.where(Document.folder_id.is_(None))
    else:
        stmt = stmt.where(Document.folder_id == folder_id)
    if scope == SCOPE_PERSONAL and owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
    if scope in ORG_SCOPES and dept_id:
        stmt = stmt.where(Document.dept_id == dept_id)
    return int(db.scalar(stmt) or 0)


def list_kb_folders(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
) -> dict:
    norm_scope, norm_dept, owner_id = _normalize_folder_scope(
        db, user, scope=scope, dept_id=dept_id
    )

    stmt = select(DocumentLibraryFolder).where(
        DocumentLibraryFolder.scope == norm_scope
    )
    if norm_scope == SCOPE_PERSONAL:
        stmt = stmt.where(DocumentLibraryFolder.owner_id == user.id)
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
    items: list[dict] = []

    uncategorized_count = _count_docs_in_folder(
        db,
        scope=norm_scope,
        folder_id=None,
        dept_id=norm_dept,
        owner_id=owner_id if norm_scope == SCOPE_PERSONAL else None,
    )
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

    for folder in rows:
        if not _folder_visible_to_user(db, user, folder):
            continue
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
                "document_count": _count_docs_in_folder(
                    db,
                    scope=norm_scope,
                    folder_id=folder.id,
                    dept_id=norm_dept,
                    owner_id=owner_id if norm_scope == SCOPE_PERSONAL else None,
                ),
                "can_manage": can_manage,
            }
        )

    return {
        "scope": norm_scope,
        "dept_id": norm_dept,
        "can_manage_folders": can_manage,
        "items": items,
    }


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
