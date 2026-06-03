"""删除平台用户时清理文档、文档库文件夹与 KnowFlow 向量索引。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document, DocumentLibraryFolder
from app.models.org import User
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_link import RagflowAccountLink
from app.models.ragflow_scope_dataset import SCOPE_PERSONAL as REG_PERSONAL
from app.services.documents.lifecycle import purge_document_completely
from app.services.ragflow_naming import (
    dataset_display_label_personal,
    dataset_name_for_personal,
    legacy_dataset_name_for_personal,
    legacy_dataset_name_for_platform_user,
)

logger = logging.getLogger(__name__)


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


def _purge_user_personal_knowledge_base(db: Session, user: User) -> None:
    from app.services.ragflow_scope_service import _get_registry, _privileged_rag_client

    reg = _get_registry(db, REG_PERSONAL, str(user.id))
    ds_ids: set[str] = set()
    if reg and (reg.ragflow_dataset_id or "").strip():
        ds_ids.add(reg.ragflow_dataset_id.strip())

    priv = _privileged_rag_client(db)
    if priv:
        found = priv.find_dataset_by_names(_personal_kb_lookup_names(db, user))
        if found and found.get("id"):
            ds_ids.add(str(found["id"]).strip())
        for ds_id in ds_ids:
            try:
                priv.delete_dataset(ds_id)
                logger.info(
                    "已删除用户 %s 的个人知识库 KnowFlow dataset=%s",
                    user.username,
                    ds_id,
                )
            except Exception as e:
                logger.warning(
                    "API 删除用户 %s 个人知识库失败 dataset=%s: %s",
                    user.username,
                    ds_id,
                    e,
                )
                from app.services.ragflow_scope_service import _delete_knowledgebase_mysql

                _delete_knowledgebase_mysql(ds_id)

    if reg:
        db.delete(reg)
        db.flush()


def _purge_user_document_mirrors(db: Session, user: User) -> None:
    from app.integrations.ragflow_client import RagflowClient
    from app.services.ragflow_sync_service import remove_document_mirror

    uid = user.id
    mirrors = list(
        db.scalars(
            select(RagflowDocumentMirrorLink).where(
                RagflowDocumentMirrorLink.platform_user_id == uid
            )
        ).all()
    )
    for mirror in mirrors:
        doc = db.get(Document, mirror.platform_document_id)
        if doc:
            remove_document_mirror(db, doc, user, commit_client=True)
            continue
        if mirror.dataset_id and mirror.ragflow_document_id:
            try:
                client = RagflowClient()
                if client.health_ok():
                    client.delete_documents(
                        mirror.dataset_id, [mirror.ragflow_document_id]
                    )
            except Exception as e:
                logger.warning(
                    "删除孤立分享镜像向量失败 user=%s: %s", user.username, e
                )
        db.delete(mirror)
    if mirrors:
        db.flush()


def _purge_user_owned_documents(db: Session, user: User) -> None:
    owned = list(
        db.scalars(select(Document).where(Document.owner_id == user.id)).all()
    )
    for doc in owned:
        purge_document_completely(db, doc)
    if owned:
        logger.info("已物理删除用户 %s 的 %s 篇文档", user.username, len(owned))


def _purge_user_library_folders(db: Session, user: User) -> None:
    db.execute(
        delete(DocumentLibraryFolder).where(
            DocumentLibraryFolder.owner_id == user.id
        )
    )
    db.flush()


def _purge_ragflow_account(db: Session, user: User) -> None:
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == user.id
        )
    )
    if not link:
        return
    email = (link.ragflow_email or "").strip()
    if email:
        from app.integrations.ragflow_provision import _purge_ragflow_user_by_email

        _purge_ragflow_user_by_email(email)


def purge_user_knowledge_resources(db: Session, user: User) -> dict[str, int]:
    """删除用户前：文档、MinIO、分享镜像、个人库文件夹、个人向量库、RAGFlow 账号。"""
    _purge_user_document_mirrors(db, user)
    owned_before = len(
        list(db.scalars(select(Document.id).where(Document.owner_id == user.id)).all())
    )
    _purge_user_owned_documents(db, user)
    _purge_user_library_folders(db, user)

    if get_settings().knowflow_enabled:
        try:
            from app.services.ragflow_scope_service import revoke_all_dept_kb_grants

            revoke_all_dept_kb_grants(db, user)
        except Exception as e:
            logger.warning("撤销用户部门库授权失败 %s: %s", user.username, e)
        _purge_user_personal_knowledge_base(db, user)
        _purge_ragflow_account(db, user)

    return {"documents_purged": owned_before}
