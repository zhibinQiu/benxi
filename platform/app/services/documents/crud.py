from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store

MAX_DOCUMENT_UPLOAD_BYTES = 30 * 1024 * 1024


def get_document(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.get(Document, document_id)
def is_version_uploaded(version: DocumentVersion) -> bool:
    return bool(version.file_size and (version.file_key or "").strip())
def document_has_uploaded_version(db: Session, document_id: uuid.UUID) -> bool:
    row = db.scalar(
        select(DocumentVersion.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.file_size > 0,
        )
        .limit(1)
    )
    return row is not None
def create_initial_uploaded_version(
    db: Session,
    document: Document,
    user: User,
    *,
    file_name: str,
    mime_type: str,
    content: bytes,
    checksum: str | None = None,
) -> DocumentVersion:
    """创建并落库首版文件（用于导入、订阅等服务端直传场景）。"""
    store = get_object_store()
    version = DocumentVersion(
        document_id=document.id,
        version_no=1,
        file_key=store.build_file_key(document.id, 1, file_name),
        file_name=file_name,
        mime_type=mime_type or "application/octet-stream",
        file_size=len(content),
        checksum=checksum,
        created_by=user.id,
    )
    store.put_object_bytes(version.file_key, content, mime_type)
    db.add(version)
    document.current_version_id = version.id
    db.commit()
    db.refresh(version)
    db.refresh(document)
    return version
def list_document_versions(db: Session, document_id: uuid.UUID) -> list[DocumentVersion]:
    rows = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
        ).all()
    )
    return [v for v in rows if is_version_uploaded(v)]
def resolve_current_version(
    db: Session, document: Document, *, repair: bool = True
) -> DocumentVersion | None:
    """解析当前可下载版本；若库中 current_version_id 为空但已有上传文件则自动修复。"""
    versions = list_document_versions(db, document.id)
    if not versions:
        return None
    if document.current_version_id:
        current = db.get(DocumentVersion, document.current_version_id)
        if current and is_version_uploaded(current):
            return current
    pick_id = _pick_current_version_id(db, document, versions)
    if not pick_id:
        return None
    version = next((v for v in versions if v.id == pick_id), None)
    if version and repair and document.current_version_id != pick_id:
        document.current_version_id = pick_id
        db.flush()
    return version
def _pick_current_version_id(
    db: Session, document: Document, versions: list[DocumentVersion]
) -> uuid.UUID | None:
    if not versions:
        return None
    if document.current_version_id:
        cur = next((v for v in versions if v.id == document.current_version_id), None)
        if cur and is_version_uploaded(cur):
            return cur.id
    for v in versions:
        if is_version_uploaded(v):
            return v.id
    return versions[0].id
def delete_document_version(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    *,
    deleted_by: uuid.UUID,
) -> dict:
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import forbidden

    if not can_delete_document(db, user, document):
        raise forbidden("无权删除该版本")

    if version.document_id != document.id:
        from app.core.exceptions import not_found

        raise not_found("版本不存在")

    store = get_object_store()
    key = (version.file_key or "").strip()
    if key and is_version_uploaded(version):
        try:
            store.delete_object(key)
        except Exception:
            pass

    db.delete(version)
    db.flush()

    remaining = list_document_versions(db, document.id)
    if remaining:
        document.current_version_id = _pick_current_version_id(db, document, remaining)
        db.commit()
        db.refresh(document)
        return {
            "ok": True,
            "document_deleted": False,
            "message": "版本已删除",
            "current_version_id": document.current_version_id,
        }

    document.current_version_id = None
    from app.services.documents.lifecycle import soft_delete_document

    soft_delete_document(db, document, deleted_by=deleted_by)
    return {
        "ok": True,
        "document_deleted": True,
        "message": "已无版本，文档已移入回收站",
        "current_version_id": None,
    }
def create_document(
    db: Session,
    user: User,
    *,
    title: str,
    description: str = "",
    scope: str = "personal",
    dept_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
) -> Document:
    from app.core.document_scope import resolve_create_params
    from app.services.library_folder_service import resolve_document_folder_id

    norm_scope, norm_dept = resolve_create_params(
        db, user, scope=scope, dept_id=dept_id
    )
    norm_folder_id = resolve_document_folder_id(
        db,
        user,
        scope=norm_scope,
        folder_id=folder_id,
        dept_id=norm_dept,
    )
    doc = Document(
        title=title,
        description=description,
        owner_id=user.id,
        dept_id=norm_dept,
        scope=norm_scope,
        folder_id=norm_folder_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
def prepare_upload(
    db: Session,
    user: User,
    document: Document,
    *,
    file_name: str,
    mime_type: str,
) -> tuple[DocumentVersion, str]:
    if not can_access_document(db, user, document, PermissionLevel.edit.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to upload new version")

    store = get_object_store()
    max_ver = db.scalar(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_id == document.id
        )
    )
    version_no = (max_ver or 0) + 1
    version = DocumentVersion(
        document_id=document.id,
        version_no=version_no,
        file_key=store.build_file_key(document.id, version_no, file_name),
        file_name=file_name,
        mime_type=mime_type,
        file_size=0,
        created_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    upload_url = store.presigned_put(version.file_key, mime_type)
    return version, upload_url


def complete_upload(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    *,
    file_size: int,
    checksum: str | None,
) -> Document:
    if not can_access_document(db, user, document, PermissionLevel.edit.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to complete upload")
    if file_size > MAX_DOCUMENT_UPLOAD_BYTES:
        from app.core.exceptions import bad_request

        raise bad_request("单文件大小不能超过 30MB")

    version.file_size = file_size
    version.checksum = checksum
    document.current_version_id = version.id
    db.commit()
    db.refresh(document)
    return document
def move_document_to_folder(
    db: Session,
    user: User,
    document: Document,
    *,
    folder_id: uuid.UUID | None,
) -> Document:
    from app.core.document_scope import VALID_SCOPES, can_edit_document
    from app.core.exceptions import bad_request, forbidden
    from app.services.library_folder_service import resolve_document_folder_id

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可移动")
    if not can_edit_document(db, user, document):
        raise forbidden("无权移动该文档")
    scope = (document.scope or "personal").strip()
    if scope not in VALID_SCOPES:
        raise bad_request("该文档分级不支持文件夹")

    norm_folder_id = resolve_document_folder_id(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        dept_id=document.dept_id,
    )
    document.folder_id = norm_folder_id
    db.commit()
    db.refresh(document)
    return document
def update_document(
    db: Session,
    user: User,
    document: Document,
    *,
    title: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    dept_id: uuid.UUID | None = None,
) -> Document:
    from app.core.document_scope import can_edit_document
    from app.core.exceptions import bad_request, forbidden

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可编辑")
    if scope is not None:
        publish_document_scope(db, user, document, scope=scope, dept_id=dept_id)
    if title is not None or description is not None:
        if not can_edit_document(db, user, document):
            raise forbidden("无权编辑该文档")
        if title is not None:
            t = title.strip()
            if not t:
                raise bad_request("标题不能为空")
            document.title = t[:512]
        if description is not None:
            document.description = description
    db.commit()
    db.refresh(document)
    return document
def publish_document_scope(
    db: Session,
    user: User,
    document: Document,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
) -> Document:
    """将文档发布到公司/部门文库（改 scope，在对应 Tab 展示，不进「分享」）。"""
    from app.core.document_scope import (
        SCOPE_COMPANY,
        SCOPE_DEPARTMENT,
        SCOPE_PERSONAL,
        resolve_create_params,
    )
    from app.core.exceptions import bad_request, forbidden
    from app.core.permissions import user_is_superuser

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可发布")
    if scope == SCOPE_PERSONAL:
        raise bad_request("请使用文档库「我的」分级存放个人文档")
    if document.owner_id != user.id and not user_is_superuser(db, user):
        raise forbidden("仅文档创建人可发布到部门/公司文库")
    norm_scope, norm_dept = resolve_create_params(db, user, scope=scope, dept_id=dept_id)
    document.scope = norm_scope
    document.dept_id = norm_dept if norm_scope == SCOPE_DEPARTMENT else None
    document.folder_id = None
    db.flush()
    return document
def update_document_status(db: Session, document: Document, status: str) -> Document:
    from app.models.document import DocumentStatus

    allowed = {DocumentStatus.active.value, DocumentStatus.disabled.value}
    if status not in allowed:
        from app.core.exceptions import bad_request

        raise bad_request("状态仅支持 active（启用）或 disabled（关闭）")
    document.status = status
    if status == DocumentStatus.disabled.value:
        from app.services.ragflow_sync_service import remove_platform_document_from_knowflow

        remove_platform_document_from_knowflow(db, document)
    db.commit()
    db.refresh(document)
    return document
