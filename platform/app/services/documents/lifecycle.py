from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store



def soft_delete_document(
    db: Session, document: Document, *, deleted_by: uuid.UUID
) -> Document:
    from datetime import datetime, timezone

    document.deleted_at = datetime.now(timezone.utc)
    document.deleted_by = deleted_by
    from app.services.ragflow_sync_service import remove_platform_document_from_knowflow

    remove_platform_document_from_knowflow(db, document)
    db.commit()
    db.refresh(document)
    return document
def restore_document(db: Session, document: Document) -> Document:
    document.deleted_at = None
    document.deleted_by = None
    db.commit()
    db.refresh(document)
    return document
def can_permanently_delete_document(db: Session, user: User, document: Document) -> bool:
    """仅可彻底删除回收站中的文档（本人删除的或系统管理员）。"""
    if document.deleted_at is None:
        return False
    if document.deleted_by == user.id:
        return True
    from app.core.permissions import user_is_superuser

    return user_is_superuser(db, user)
def _purge_jobs_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.job import Job, JobEvent

    doc_str = str(document_id)
    job_ids: set[uuid.UUID] = set(
        db.scalars(select(Job.id).where(Job.document_id == document_id)).all()
    )
    for job in db.scalars(select(Job)).all():
        payload = job.payload or {}
        if payload.get("document_id") == doc_str:
            job_ids.add(job.id)
    if not job_ids:
        return
    db.execute(delete(JobEvent).where(JobEvent.job_id.in_(job_ids)))
    db.execute(delete(Job).where(Job.id.in_(job_ids)))
def _purge_import_links_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.feed_subscription import FeedEntryImport
    from app.models.wechat_mp import WechatMpArticleImport

    db.execute(
        delete(FeedEntryImport).where(FeedEntryImport.document_id == document_id)
    )
    db.execute(
        delete(WechatMpArticleImport).where(
            WechatMpArticleImport.document_id == document_id
        )
    )
def _purge_compare_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.compare import CompareJob

    doc_str = str(document_id)
    compare_ids: set[uuid.UUID] = set(
        db.scalars(
            select(CompareJob.id).where(CompareJob.base_document_id == document_id)
        ).all()
    )
    for job in db.scalars(select(CompareJob)).all():
        ids = job.document_ids or []
        if doc_str in ids or str(job.base_document_id) == doc_str:
            compare_ids.add(job.id)
    if compare_ids:
        db.execute(delete(CompareJob).where(CompareJob.id.in_(compare_ids)))
def _purge_rag_sessions_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.rag import RagMessage, RagSession

    doc_str = str(document_id)
    session_ids: list[uuid.UUID] = []
    for session in db.scalars(select(RagSession)).all():
        doc_ids = session.document_ids or []
        if doc_str in doc_ids:
            session_ids.append(session.id)
    if not session_ids:
        return
    db.execute(delete(RagMessage).where(RagMessage.session_id.in_(session_ids)))
    db.execute(delete(RagSession).where(RagSession.id.in_(session_ids)))
def _purge_document_storage(db: Session, document: Document) -> None:
    versions = list(
        db.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        ).all()
    )
    store = get_object_store()
    for version in versions:
        key = (version.file_key or "").strip()
        if key and is_version_uploaded(version):
            try:
                store.delete_object(key)
            except Exception:
                pass
def purge_document_completely(db: Session, document: Document) -> None:
    """物理清除文档及关联任务、索引、对象存储（不可恢复）。"""
    from app.models.ragflow_document_link import RagflowDocumentLink
    from app.services.ragflow_sync_service import remove_platform_document_from_knowflow

    doc_id = document.id
    remove_platform_document_from_knowflow(db, document)
    _purge_jobs_for_document(db, doc_id)
    _purge_compare_for_document(db, doc_id)
    _purge_rag_sessions_for_document(db, doc_id)
    _purge_import_links_for_document(db, doc_id)
    _purge_document_storage(db, document)
    db.execute(
        delete(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == doc_id
        )
    )
    db.execute(
        delete(DocumentPermission).where(DocumentPermission.document_id == doc_id)
    )
    # 先解除 current_version 引用，再删版本，避免 ORM 将 document_id 置空
    document.current_version_id = None
    db.flush()
    db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == doc_id))
    db.execute(delete(Document).where(Document.id == doc_id))
    db.flush()
def permanently_delete_document(
    db: Session, user: User, document: Document, *, commit: bool = True
) -> None:
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import forbidden

    if document.deleted_at is None:
        if not can_delete_document(db, user, document):
            raise forbidden("无权删除该文档")
    elif not can_permanently_delete_document(db, user, document):
        raise forbidden("无权彻底删除该文档")

    purge_document_completely(db, document)
    if commit:
        db.commit()
def batch_delete_documents(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
    *,
    permanent: bool = False,
) -> dict[str, list[str] | int]:
    """批量删除；彻底删除在单事务内提交，避免外键残留导致 500。"""
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import AppError
    from app.services.documents.crud import get_document

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    seen: set[uuid.UUID] = set()

    try:
        for doc_id in document_ids:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            doc = get_document(db, doc_id)
            if not doc:
                failed.append({"id": str(doc_id), "message": "文档不存在"})
                continue
            try:
                if permanent:
                    permanently_delete_document(db, user, doc, commit=False)
                else:
                    if doc.deleted_at is not None:
                        failed.append({"id": str(doc_id), "message": "文档已在回收站"})
                        continue
                    if not can_delete_document(db, user, doc):
                        failed.append({"id": str(doc_id), "message": "无权删除该文档"})
                        continue
                    soft_delete_document(db, doc, deleted_by=user.id)
                deleted.append(str(doc_id))
            except AppError as e:
                detail = e.detail if isinstance(e.detail, dict) else {}
                failed.append(
                    {
                        "id": str(doc_id),
                        "message": str(detail.get("message") or e),
                    }
                )
        if permanent and deleted:
            db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_count": len(deleted),
    }
def empty_recycle_bin(db: Session, user: User) -> int:
    """彻底删除当前用户回收站中的全部文档。"""
    from app.services.documents.listing import list_recycle_documents

    docs, _ = list_recycle_documents(db, user, page=1, page_size=10_000)
    doc_ids = [d.id for d in docs]
    count = 0
    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        if not doc or doc.deleted_at is None:
            continue
        if not can_permanently_delete_document(db, user, doc):
            continue
        purge_document_completely(db, doc)
        count += 1
    if count:
        db.commit()
    return count
