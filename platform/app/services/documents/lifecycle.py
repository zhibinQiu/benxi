from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store

_BATCH_DELETE_MAX_WORKERS = 8


def soft_delete_document(
    db: Session, document: Document, *, deleted_by: uuid.UUID
) -> Document:
    """兼容旧调用：等同永久删除（不再使用回收站）。"""
    from app.services.ragflow_sync_service import schedule_knowflow_deletes

    targets = purge_document_completely(db, document, defer_knowflow=True)
    db.commit()
    schedule_knowflow_deletes(targets)
    return document


def restore_document(
    db: Session, document: Document, *, user_id: uuid.UUID | None = None
) -> Document:
    document.deleted_at = None
    document.deleted_by = None
    db.commit()
    db.refresh(document)
    if user_id is not None:
        from app.core.platform_cache import invalidate_document_caches

        invalidate_document_caches(str(user_id))
    return document


def can_permanently_delete_document(db: Session, user: User, document: Document) -> bool:
    from app.core.document_scope import can_delete_document

    return can_delete_document(db, user, document)


def _purge_jobs_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.job import Job, JobEvent

    doc_str = str(document_id)
    job_ids: set[uuid.UUID] = set(
        db.scalars(select(Job.id).where(Job.document_id == document_id)).all()
    )
    payload_job_ids = db.scalars(
        select(Job.id).where(Job.payload["document_id"].astext == doc_str)
    ).all()
    job_ids.update(payload_job_ids)
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
    compare_ids.update(
        db.scalars(
            select(CompareJob.id).where(CompareJob.document_ids.contains([doc_str]))
        ).all()
    )
    if compare_ids:
        db.execute(delete(CompareJob).where(CompareJob.id.in_(compare_ids)))


def _purge_rag_sessions_for_document(db: Session, document_id: uuid.UUID) -> None:
    from app.models.rag import RagMessage, RagSession

    doc_str = str(document_id)
    session_ids = list(
        db.scalars(
            select(RagSession.id).where(
                RagSession.document_ids.contains([doc_str])
            )
        ).all()
    )
    if not session_ids:
        return
    db.execute(delete(RagMessage).where(RagMessage.session_id.in_(session_ids)))
    db.execute(delete(RagSession).where(RagSession.id.in_(session_ids)))


def _purge_document_external_resources(document: Document) -> None:
    """线程安全的对象存储与 Git 仓清理（不访问数据库）。"""
    from app.services.document_git_service import remove_document_git_repo

    try:
        get_object_store().delete_prefix(f"docs/{document.id}/")
    except Exception:
        pass
    remove_document_git_repo(document.id)


def purge_document_completely(
    db: Session,
    document: Document,
    *,
    defer_knowflow: bool = False,
    skip_external: bool = False,
) -> list:
    """物理清除文档及关联任务、索引、对象存储（不可恢复）。"""
    from app.models.ragflow_document_link import RagflowDocumentLink
    from app.services.ragflow_sync_service import (
        KnowflowDeleteTarget,
        detach_platform_document_knowflow,
    )

    doc_id = document.id
    targets: list[KnowflowDeleteTarget] = detach_platform_document_knowflow(
        db, document, sync_remote=not defer_knowflow
    )
    _purge_jobs_for_document(db, doc_id)
    _purge_compare_for_document(db, doc_id)
    _purge_rag_sessions_for_document(db, doc_id)
    _purge_import_links_for_document(db, doc_id)
    if not skip_external:
        _purge_document_external_resources(document)
    db.execute(
        delete(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == doc_id
        )
    )
    db.execute(
        delete(DocumentPermission).where(DocumentPermission.document_id == doc_id)
    )
    document.current_version_id = None
    db.flush()
    db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == doc_id))
    db.execute(delete(Document).where(Document.id == doc_id))
    db.flush()
    return targets


def permanently_delete_document(
    db: Session,
    user: User,
    document: Document,
    *,
    commit: bool = True,
    defer_knowflow: bool = False,
) -> list:
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import forbidden
    from app.services.ragflow_sync_service import schedule_knowflow_deletes

    if not can_delete_document(db, user, document):
        raise forbidden("无权删除该文档")

    targets = purge_document_completely(db, document, defer_knowflow=defer_knowflow)
    if commit:
        db.commit()
        from app.core.platform_cache import invalidate_document_caches

        invalidate_document_caches(str(user.id))
    if defer_knowflow and targets:
        schedule_knowflow_deletes(targets)
    return targets


def _purge_documents_external_parallel(documents: list[Document]) -> None:
    if not documents:
        return
    if len(documents) == 1:
        _purge_document_external_resources(documents[0])
        return
    workers = min(_BATCH_DELETE_MAX_WORKERS, len(documents))
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="doc-purge"
    ) as pool:
        list(pool.map(_purge_document_external_resources, documents))


def batch_delete_documents(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
    *,
    permanent: bool = True,
) -> dict[str, list[str] | int]:
    """批量永久删除文档及知识库索引（单事务提交，KnowFlow 远端异步清理）。"""
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import AppError
    from app.services.documents.crud import get_document
    from app.services.ragflow_sync_service import schedule_knowflow_deletes

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    seen: set[uuid.UUID] = set()
    all_targets: list = []
    to_purge: list[Document] = []

    try:
        for doc_id in document_ids:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            doc = get_document(db, doc_id)
            if not doc:
                failed.append({"id": str(doc_id), "message": "文档不存在"})
                continue
            if not can_delete_document(db, user, doc):
                failed.append({"id": str(doc_id), "message": "无权删除该文档"})
                continue
            to_purge.append(doc)

        if to_purge:
            _purge_documents_external_parallel(to_purge)
            for doc in to_purge:
                try:
                    targets = purge_document_completely(
                        db, doc, defer_knowflow=True, skip_external=True
                    )
                    all_targets.extend(targets)
                    deleted.append(str(doc.id))
                except AppError as e:
                    detail = e.detail if isinstance(e.detail, dict) else {}
                    failed.append(
                        {
                            "id": str(doc.id),
                            "message": str(detail.get("message") or e),
                        }
                    )
        if deleted:
            db.commit()
            schedule_knowflow_deletes(all_targets)
            from app.core.platform_cache import invalidate_document_caches

            invalidate_document_caches(str(user.id))
    except Exception:
        db.rollback()
        raise

    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_count": len(deleted),
    }


def empty_recycle_bin(db: Session, user: User) -> int:
    """兼容旧 API：清空回收站中当前用户可删的文档。"""
    from app.services.documents.listing import list_recycle_documents

    docs, _ = list_recycle_documents(db, user, page=1, page_size=10_000)
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return 0
    result = batch_delete_documents(db, user, doc_ids, permanent=True)
    return int(result.get("deleted_count") or 0)
