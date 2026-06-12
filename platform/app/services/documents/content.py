from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.services.documents.crud import get_document, resolve_current_version
from app.storage.object_store import get_object_store


def _is_compareable_version(version: DocumentVersion) -> bool:
    from app.core.document_format import is_compareable_file

    return is_compareable_file(version.file_name, version.mime_type)
def _is_pdf_version(version: DocumentVersion) -> bool:
    mime = (version.mime_type or "").lower()
    if "pdf" in mime:
        return True
    return (version.file_name or "").lower().endswith(".pdf")
def read_document_pdf_bytes(
    db: Session, user: User, document_id: uuid.UUID
) -> tuple[bytes, str, Document]:
    """读取文档当前版本 PDF 内容；校验「可查询」权限（翻译/对比/检索）。"""
    from app.core.exceptions import bad_request, forbidden, not_found
    from app.models.document import DocumentStatus

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    if doc.status != DocumentStatus.active.value:
        raise bad_request("文档已关闭或不可用")
    if not can_access_document(db, user, doc, PermissionLevel.query.value):
        raise forbidden("无权查询或使用该文档")
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
    if not can_access_document(db, user, document, PermissionLevel.visible.value):
        return None
    version = resolve_current_version(db, document)
    if not version:
        return None
    return get_object_store().presigned_get(version.file_key)
def read_document_file_bytes(
    db: Session,
    user: User,
    document: Document,
    *,
    version_id: uuid.UUID | None = None,
) -> tuple[bytes, str, str]:
    """读取指定或当前版本文件（经平台 API 代理下载，避免浏览器无法访问 MinIO 内网地址）。"""
    from app.core.exceptions import bad_request, forbidden, not_found
    from app.models.document import DocumentStatus

    if document.deleted_at is not None:
        raise not_found("文档不存在")
    if document.status != DocumentStatus.active.value:
        raise bad_request("文档已关闭或不可用")
    if not can_access_document(db, user, document, PermissionLevel.visible.value):
        raise forbidden("无权下载该文档")
    if version_id is not None:
        version = db.get(DocumentVersion, version_id)
        if not version or version.document_id != document.id:
            raise not_found("版本不存在")
    else:
        version = resolve_current_version(db, document)
    if not version or not version.file_key:
        raise bad_request("文档尚未上传文件")
    data = get_object_store().get_object_bytes(version.file_key)
    file_name = version.file_name or "document"
    mime = version.mime_type or "application/octet-stream"
    return data, file_name, mime
