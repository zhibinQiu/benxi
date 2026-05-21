from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store


def list_accessible_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible = [d for d in candidates if can_access_document(db, user, d, PermissionLevel.read.value)]
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


def get_document(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.get(Document, document_id)


def create_document(
    db: Session,
    user: User,
    *,
    title: str,
    description: str = "",
    dept_id: uuid.UUID | None = None,
) -> Document:
    doc = Document(
        title=title,
        description=description,
        owner_id=user.id,
        dept_id=dept_id,
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
    if not can_access_document(db, user, document, PermissionLevel.use.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to upload new version")

    max_ver = db.scalar(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_id == document.id
        )
    )
    version_no = (max_ver or 0) + 1
    store = get_object_store()
    file_key = store.build_file_key(document.id, version_no, file_name)
    version = DocumentVersion(
        document_id=document.id,
        version_no=version_no,
        file_key=file_key,
        file_name=file_name,
        mime_type=mime_type,
        created_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    upload_url = store.presigned_put(file_key, mime_type)
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
    if not can_access_document(db, user, document, PermissionLevel.use.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to complete upload")

    version.file_size = file_size
    version.checksum = checksum
    document.current_version_id = version.id
    db.commit()
    db.refresh(document)
    return document


def grant_permission(
    db: Session,
    user: User,
    document: Document,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    level: str,
    expires_at,
) -> DocumentPermission:
    if document.owner_id != user.id and not _can_grant(db, user):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to grant access")

    perm = DocumentPermission(
        document_id=document.id,
        subject_type=subject_type,
        subject_id=subject_id,
        level=level,
        granted_by=user.id,
        expires_at=expires_at,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def _can_grant(db: Session, user: User) -> bool:
    from app.core.permissions import user_has_permission

    return user_has_permission(db, user, "doc.grant") or user_has_permission(
        db, user, "admin.user"
    )


def list_document_permissions(
    db: Session, document_id: uuid.UUID
) -> list[DocumentPermission]:
    return list(
        db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document_id
            )
        ).all()
    )


def revoke_permission(db: Session, perm_id: uuid.UUID) -> None:
    perm = db.get(DocumentPermission, perm_id)
    if perm:
        db.delete(perm)
        db.commit()


def soft_delete_document(db: Session, document: Document) -> Document:
    from datetime import datetime, timezone

    document.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document


def _is_pdf_version(version: DocumentVersion) -> bool:
    mime = (version.mime_type or "").lower()
    if "pdf" in mime:
        return True
    return (version.file_name or "").lower().endswith(".pdf")


def list_translatable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """当前用户有「使用」权限、已上传 PDF 当前版本的文档。"""
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    rows: list[tuple[Document, DocumentVersion]] = []
    for doc in candidates:
        if not doc.current_version_id:
            continue
        if not can_access_document(db, user, doc, PermissionLevel.use.value):
            continue
        version = db.get(DocumentVersion, doc.current_version_id)
        if not version or not _is_pdf_version(version):
            continue
        rows.append((doc, version))
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total


def read_document_pdf_bytes(
    db: Session, user: User, document_id: uuid.UUID
) -> tuple[bytes, str, Document]:
    """读取文档当前版本 PDF 内容；校验「使用」权限。"""
    from app.core.exceptions import bad_request, forbidden, not_found

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    if not can_access_document(db, user, doc, PermissionLevel.use.value):
        raise forbidden("无权使用该文档")
    if not doc.current_version_id:
        raise bad_request("文档尚未上传文件")
    version = db.get(DocumentVersion, doc.current_version_id)
    if not version:
        raise bad_request("文档版本不存在")
    if not _is_pdf_version(version):
        raise bad_request("仅支持 PDF 文档翻译")
    data = get_object_store().get_object_bytes(version.file_key)
    return data, version.file_name, doc


def get_download_url(
    db: Session, user: User, document: Document
) -> str | None:
    if not can_access_document(db, user, document, PermissionLevel.read.value):
        return None
    if not document.current_version_id:
        return None
    version = db.get(DocumentVersion, document.current_version_id)
    if not version:
        return None
    return get_object_store().presigned_get(version.file_key)
