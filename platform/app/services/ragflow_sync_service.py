"""平台文档 ↔ KnowFlow：按分级单库同步一份，权限由 RBAC 授权。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import _document_scope
from app.core.permissions import PermissionLevel, can_access_document
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.integrations.ragflow_client import RagflowClient
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.services.document_service import list_queryable_documents
from app.services.ragflow_scope_service import (
    resolve_dataset_for_document,
    sync_document_kb_grants,
)

logger = logging.getLogger(__name__)


def _get_link(db: Session, document_id: uuid.UUID) -> RagflowDocumentLink | None:
    return db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document_id
        )
    )


def remove_platform_document_from_knowflow(db: Session, document: Document) -> bool:
    """平台文档删除/关闭时，从 KnowFlow 知识库移除索引并删除映射。"""
    link = _get_link(db, document.id)
    if not link:
        return False
    try:
        client = RagflowClient()
        if client.health_ok() and link.dataset_id and link.ragflow_document_id:
            client.delete_documents(link.dataset_id, [link.ragflow_document_id])
    except Exception as e:
        logger.warning(
            "从 KnowFlow 删除文档失败 platform_doc=%s: %s",
            document.id,
            e,
        )
    db.delete(link)
    db.flush()
    return True


def sync_document_to_knowflow(
    db: Session, user: User, document: Document, *, force: bool = False
) -> str | None:
    """将文档同步到对应分级知识库（公司/部门/个人仅一份），并同步 KB 授权。"""
    if document.deleted_at is not None:
        return None
    if not can_access_document(db, user, document, PermissionLevel.query.value):
        return None
    if not document.current_version_id:
        return None

    kf = get_knowflow_client_for_user(db, user)
    if not kf.enabled():
        return None

    target_ds = resolve_dataset_for_document(db, user, document, kf)
    if not target_ds:
        return None

    existing = _get_link(db, document.id)
    if existing and not force:
        if existing.dataset_id == target_ds:
            sync_document_kb_grants(db, document)
            return existing.ragflow_document_id
        force = True

    version = db.get(DocumentVersion, document.current_version_id)
    if not version:
        return None

    from app.storage.object_store import get_object_store

    store = get_object_store()
    content = store.get_object_bytes(version.file_key)
    rag_doc_id = kf.sync_platform_document(
        platform_document_id=document.id,
        file_name=version.file_name,
        content=content,
        mime_type=version.mime_type,
        dataset_id=target_ds,
    )
    if not rag_doc_id:
        return None

    if existing:
        existing.ragflow_document_id = rag_doc_id
        existing.dataset_id = target_ds
        existing.platform_user_id = user.id
        existing.file_name = version.file_name
    else:
        db.add(
            RagflowDocumentLink(
                platform_document_id=document.id,
                platform_user_id=user.id,
                ragflow_document_id=rag_doc_id,
                dataset_id=target_ds,
                file_name=version.file_name,
            )
        )
    db.flush()
    sync_document_kb_grants(db, document)
    return rag_doc_id


def purge_stale_knowflow_links(db: Session) -> int:
    """清理已删除或已关闭平台文档在 KnowFlow 中的残留索引。"""
    from app.models.document import DocumentStatus

    removed = 0
    for link in list(db.scalars(select(RagflowDocumentLink)).all()):
        doc = db.get(Document, link.platform_document_id)
        stale = (
            doc is None
            or doc.deleted_at is not None
            or doc.status != DocumentStatus.active.value
        )
        if not stale:
            continue
        ref = doc if doc is not None else Document(id=link.platform_document_id)
        if remove_platform_document_from_knowflow(db, ref):
            removed += 1
    if removed:
        db.commit()
    return removed


def sync_accessible_documents(
    db: Session, user: User, *, limit: int = 50
) -> dict[str, str]:
    """将用户可查询的平台文档同步到分级 KnowFlow 库（公司/部门/个人/分享授权，对齐「所有」）。"""
    mapping: dict[str, str] = {}
    page = 1
    page_size = max(min(limit, 100), 20) if limit > 0 else 50
    new_synced = 0

    while limit <= 0 or new_synced < limit:
        docs, total = list_queryable_documents(
            db, user, page=page, page_size=page_size
        )
        if not docs:
            break
        for doc in docs:
            existing = _get_link(db, doc.id)
            if existing:
                try:
                    sync_document_kb_grants(db, doc)
                except Exception as e:
                    logger.debug("刷新 KnowFlow 授权跳过 %s: %s", doc.id, e)
                continue
            if limit > 0 and new_synced >= limit:
                return mapping
            rid = sync_document_to_knowflow(db, user, doc)
            if rid:
                mapping[str(doc.id)] = rid
                new_synced += 1
        if page * page_size >= total:
            break
        page += 1

    return mapping


def allowed_ragflow_doc_map(
    db: Session, user: User, platform_document_ids: list[str]
) -> dict[str, str]:
    """平台文档 ID → RAGFlow 文档 ID（仅含当前用户具备「可查询」权限的文档）。"""
    if not get_knowflow_client_for_user(db, user).enabled():
        return {}
    out: dict[str, str] = {}
    for pid in platform_document_ids:
        try:
            did = uuid.UUID(pid)
        except ValueError:
            continue
        doc = db.get(Document, did)
        if not doc or not can_access_document(
            db, user, doc, PermissionLevel.query.value
        ):
            continue
        link = _get_link(db, did)
        if link:
            out[pid] = link.ragflow_document_id
    return out
