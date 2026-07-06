"""删除平台用户时清理文档、文档库文件夹与 KnowFlow 向量索引。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document, DocumentLibraryFolder
from app.models.org import User
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_link import RagflowAccountLink
from app.models.ragflow_scope_dataset import SCOPE_PERSONAL as REG_PERSONAL
from app.services.documents.lifecycle import (
    purge_document_completely,
    schedule_documents_external_purge,
)
from app.services.ragflow_naming import (
    dataset_display_label_personal,
    dataset_name_for_personal,
    legacy_dataset_name_for_personal,
    legacy_dataset_name_for_platform_user,
)
from app.services.ragflow_sync_service import KnowflowDeleteTarget, schedule_knowflow_deletes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserKnowflowPurgeJob:
    dataset_ids: tuple[str, ...]
    lookup_names: tuple[str, ...]
    ragflow_email: str | None
    user_id_suffix: str


def _personal_kb_lookup_names(db: Session, user: User) -> list[str]:
    return list(
        dict.fromkeys(
            n
            for n in (
                dataset_display_label_personal(db, user.id),
                dataset_name_for_personal(user.id, db),
                legacy_dataset_name_for_personal(user.id),
                legacy_dataset_name_for_platform_user(user.id),
                (user.display_name or "").strip(),
                (user.username or "").strip(),
            )
            if n
        )
    )


def _collect_personal_kb_purge_job(db: Session, user: User) -> UserKnowflowPurgeJob | None:
    from app.services.ragflow_scope_service import _get_registry

    ds_ids: set[str] = set()
    reg = _get_registry(db, REG_PERSONAL, str(user.id))
    if reg and (reg.ragflow_dataset_id or "").strip():
        ds_ids.add(reg.ragflow_dataset_id.strip())
        db.delete(reg)
        db.flush()

    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == user.id
        )
    )
    email = (link.ragflow_email or "").strip() if link else None
    suffix = str(user.id).replace("-", "")[-8:].lower()

    lookup_names = tuple(_personal_kb_lookup_names(db, user))
    if not ds_ids and not lookup_names and not email:
        return None
    return UserKnowflowPurgeJob(
        dataset_ids=tuple(ds_ids),
        lookup_names=lookup_names,
        ragflow_email=email or None,
        user_id_suffix=suffix,
    )


def schedule_user_knowflow_external_purge(job: UserKnowflowPurgeJob) -> None:
    """后台清理个人向量库与 RAGFlow 账号，避免删除用户请求阻塞在远端。"""

    def run() -> None:
        from app.database import SessionLocal
        from app.integrations.ragflow_provision import (
            _purge_ragflow_user_by_email,
            _purge_ragflow_user_by_uid_suffix,
        )
        from app.services.ragflow_scope_service import (
            _delete_knowledgebase_mysql,
            _privileged_rag_client,
        )

        ds_ids: set[str] = set(job.dataset_ids)
        db = SessionLocal()
        try:
            priv = _privileged_rag_client(db)
        finally:
            db.close()
        if priv and job.lookup_names:
            found = priv.find_dataset_by_names(list(job.lookup_names))
            if found and found.get("id"):
                ds_ids.add(str(found["id"]).strip())
        for ds_id in ds_ids:
            deleted = False
            if priv:
                try:
                    priv.delete_dataset(ds_id)
                    deleted = True
                    logger.info("后台已删除个人知识库 dataset=%s", ds_id)
                except Exception as e:
                    logger.warning("后台 API 删除个人知识库失败 dataset=%s: %s", ds_id, e)
            if not deleted:
                _delete_knowledgebase_mysql(ds_id)

        if job.ragflow_email:
            _purge_ragflow_user_by_email(job.ragflow_email)
        elif job.user_id_suffix:
            _purge_ragflow_user_by_uid_suffix(job.user_id_suffix)

    from app.core.background_executor import submit_background

    submit_background("user-knowflow-purge", run)


def _purge_user_document_mirrors(
    db: Session, user: User
) -> list[KnowflowDeleteTarget]:
    uid = user.id
    targets: list[KnowflowDeleteTarget] = []
    mirrors = list(
        db.scalars(
            select(RagflowDocumentMirrorLink).where(
                RagflowDocumentMirrorLink.platform_user_id == uid
            )
        ).all()
    )
    for mirror in mirrors:
        if mirror.dataset_id and mirror.ragflow_document_id:
            targets.append(
                KnowflowDeleteTarget(
                    dataset_id=mirror.dataset_id,
                    ragflow_document_id=mirror.ragflow_document_id,
                )
            )
        db.delete(mirror)
    if mirrors:
        db.flush()
    return targets


def _purge_user_owned_documents(
    db: Session, user: User
) -> tuple[int, list[uuid.UUID], list[KnowflowDeleteTarget]]:
    owned = list(
        db.scalars(select(Document).where(Document.owner_id == user.id)).all()
    )
    purge_ids: list[uuid.UUID] = []
    targets: list[KnowflowDeleteTarget] = []
    for doc in owned:
        doc_targets = purge_document_completely(
            db, doc, defer_knowflow=True, skip_external=True
        )
        targets.extend(doc_targets)
        purge_ids.append(doc.id)
    if owned:
        logger.info("已物理删除用户 %s 的 %s 篇文档", user.username, len(owned))
    return len(owned), purge_ids, targets


def _purge_user_library_folders(db: Session, user: User) -> None:
    db.execute(
        delete(DocumentLibraryFolder).where(
            DocumentLibraryFolder.owner_id == user.id
        )
    )
    db.flush()


def purge_user_knowledge_resources(db: Session, user: User) -> dict[str, int]:
    """删除用户前：文档、分享镜像、个人库文件夹；MinIO/KnowFlow 远端异步清理。"""
    mirror_targets = _purge_user_document_mirrors(db, user)
    owned_count, purge_doc_ids, doc_targets = _purge_user_owned_documents(db, user)
    _purge_user_library_folders(db, user)

    knowflow_job: UserKnowflowPurgeJob | None = None
    if get_settings().knowflow_enabled:
        knowflow_job = _collect_personal_kb_purge_job(db, user)

    all_targets = mirror_targets + doc_targets
    if purge_doc_ids:
        schedule_documents_external_purge(purge_doc_ids)
    if all_targets:
        schedule_knowflow_deletes(all_targets)
    if knowflow_job:
        schedule_user_knowflow_external_purge(knowflow_job)

    return {"documents_purged": owned_count}
