"""文档公开分享令牌。"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.services.documents.crud import resolve_current_version
from app.storage.object_store import get_object_store


def new_share_token() -> str:
    """生成公开分享令牌（URL-safe）。"""
    return secrets.token_urlsafe(32)


def ensure_share_token(db: Session, document: Document) -> str:
    """确保文档有 share_token，缺失则补齐。"""
    if document.share_token:
        return document.share_token
    document.share_token = new_share_token()
    db.commit()
    db.refresh(document)
    return document.share_token or ""


def regenerate_share_token(db: Session, document: Document) -> str:
    """重新生成分享令牌（覆盖旧链接）。"""
    document.share_token = new_share_token()
    db.commit()
    db.refresh(document)
    return document.share_token or ""


def get_document_by_share_token(db: Session, share_token: str) -> Document | None:
    """根据公开分享令牌获取文档（未删除且启用）。"""
    token = (share_token or "").strip()
    if not token:
        return None
    doc = db.scalar(select(Document).where(Document.share_token == token))
    if not doc or doc.deleted_at is not None:
        return None
    if doc.status != DocumentStatus.active.value:
        return None
    return doc


def read_shared_document_file(
    db: Session, document: Document
) -> tuple[bytes, str, str, DocumentVersion]:
    """读取分享文档的当前版本文件（无需登录 ACL）。"""
    from app.core.exceptions import bad_request, not_found

    version = resolve_current_version(db, document)
    if not version or not (version.file_key or "").strip():
        raise bad_request("文档尚未上传文件")
    if not version.file_size:
        raise bad_request("文档尚未上传文件")
    data = get_object_store().get_object_bytes(version.file_key)
    file_name = version.file_name or "document"
    mime = version.mime_type or "application/octet-stream"
    return data, file_name, mime, version


def revoke_share_token(db: Session, document: Document) -> None:
    """撤销公开分享链接。"""
    document.share_token = None
    db.commit()
    db.refresh(document)
