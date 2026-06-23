"""Knowledge QA — 文档元数据."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.services.document_index_service import _batch_version_links_by_document
from app.services.document_service import resolve_current_version
from app.services.ragflow_version_link_service import resolve_latest_indexed_version


def _batch_documents(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, Document]:
    if not doc_ids:
        return {}
    rows = db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
    return {str(doc.id): doc for doc in rows}


def _batch_versions(db: Session, version_ids: list[uuid.UUID]) -> dict[str, DocumentVersion]:
    if not version_ids:
        return {}
    rows = db.scalars(select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))).all()
    return {str(ver.id): ver for ver in rows}


def _doc_titles(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, str]:
    docs_by_id = _batch_documents(db, doc_ids)
    titles: dict[str, str] = {}
    for did in doc_ids:
        doc = docs_by_id.get(str(did))
        if doc:
            titles[str(did)] = doc.title or "未命名文档"
    return titles


def _doc_citation_meta(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
    """引用卡片展示用：文件名与格式标签。"""
    from app.core.document_format import version_file_format_label

    docs_by_id = _batch_documents(db, doc_ids)
    version_links_by_doc = _batch_version_links_by_document(db, doc_ids)
    version_ids: list[uuid.UUID] = []
    for links in version_links_by_doc.values():
        for link in links:
            if link.platform_version_id:
                version_ids.append(link.platform_version_id)
    for doc in docs_by_id.values():
        if doc.current_version_id:
            version_ids.append(doc.current_version_id)

    versions_by_id = _batch_versions(db, list(dict.fromkeys(version_ids)))

    meta: dict[str, dict[str, Any]] = {}
    for did in doc_ids:
        doc = docs_by_id.get(str(did))
        if not doc:
            continue
        links = version_links_by_doc.get(str(did), [])
        ver = resolve_latest_indexed_version(db, doc, version_links=links)
        if not ver and doc.current_version_id:
            ver = versions_by_id.get(str(doc.current_version_id))
        if not ver:
            ver = resolve_current_version(db, doc)
        file_name = (ver.file_name if ver else None) or doc.title or ""
        mime_type = ver.mime_type if ver else None
        meta[str(did)] = {
            "file_name": file_name,
            "file_format": version_file_format_label(file_name, mime_type),
        }
    return meta
