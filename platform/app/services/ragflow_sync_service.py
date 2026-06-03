"""平台文档 ↔ KnowFlow：按分级单库同步一份，权限由 RBAC 授权。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    SCOPE_PERSONAL,
    _document_scope,
    has_explicit_user_query_share,
)
from app.core.permissions import PermissionLevel, can_access_document
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.integrations.ragflow_client import RagflowClient
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.services.document_service import list_queryable_documents, resolve_current_version
from app.services.ragflow_scope_service import (
    ensure_scope_dataset,
    resolve_dataset_for_document,
    sync_document_kb_grants,
)

logger = logging.getLogger(__name__)


class KnowflowSyncError(Exception):
    """文档同步 KnowFlow 失败（含用户可读原因）。"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _sync_context_for_document(
    db: Session, actor: User, document: Document
) -> tuple[User, object]:
    """个人库文档须用所有者 KnowFlow 会话上传（permission=me）。"""
    scope = _document_scope(db, document)
    owner = db.get(User, document.owner_id) if document.owner_id else None
    if scope == SCOPE_PERSONAL and owner:
        return owner, get_knowflow_client_for_user(db, owner)
    return actor, get_knowflow_client_for_user(db, actor)


def _upload_with_fallback(
    kf,
    *,
    dataset_id: str,
    file_name: str,
    content: bytes,
    mime_type: str,
    platform_document_id: uuid.UUID,
    platform_user_id: uuid.UUID | None,
) -> str | None:
    from app.services.ragflow_scope_service import _admin_rag_client

    clients = [getattr(kf, "_rag", None)]
    admin = _admin_rag_client()
    if admin and admin not in clients:
        clients.append(admin)
    last_err: Exception | None = None
    for rag in clients:
        if rag is None:
            continue
        try:
            doc = rag.upload_document(
                dataset_id,
                file_name=file_name,
                content=content,
                meta_fields={
                    "platform_document_id": str(platform_document_id),
                    "platform_user_id": str(platform_user_id or ""),
                    "mime_type": mime_type,
                },
            )
            rag_doc_id = doc.get("id") or doc.get("doc_id")
            if rag_doc_id:
                return str(rag_doc_id)
        except Exception as e:
            last_err = e
            logger.warning(
                "KnowFlow 上传重试 dataset=%s: %s",
                dataset_id,
                e,
            )
    if last_err:
        logger.warning("KnowFlow 上传全部失败 doc=%s: %s", platform_document_id, last_err)
    return None


def _get_link(db: Session, document_id: uuid.UUID) -> RagflowDocumentLink | None:
    return get_document_link(db, document_id)


def get_document_link(db: Session, document_id: uuid.UUID) -> RagflowDocumentLink | None:
    """平台文档 ↔ RAGFlow 映射（公开接口，供 API / 域层使用）。"""
    return db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document_id
        )
    )


def get_document_mirror_link(
    db: Session, document_id: uuid.UUID, user_id: uuid.UUID
) -> RagflowDocumentMirrorLink | None:
    return db.scalar(
        select(RagflowDocumentMirrorLink).where(
            RagflowDocumentMirrorLink.platform_document_id == document_id,
            RagflowDocumentMirrorLink.platform_user_id == user_id,
        )
    )


def _should_mirror_shared_document(db: Session, user: User, document: Document) -> bool:
    """显式分享 + 可查询及以上 → 镜像到接收者个人库；低于可查询不进 KnowFlow。"""
    if document.owner_id == user.id:
        return False
    if not can_access_document(db, user, document, PermissionLevel.query.value):
        return False
    return has_explicit_user_query_share(db, user, document)


def remove_document_mirror(
    db: Session, document: Document, user: User, *, commit_client: bool = True
) -> bool:
    mirror = get_document_mirror_link(db, document.id, user.id)
    if not mirror:
        return False
    if commit_client:
        try:
            client = RagflowClient()
            if client.health_ok() and mirror.dataset_id and mirror.ragflow_document_id:
                client.delete_documents(
                    mirror.dataset_id, [mirror.ragflow_document_id]
                )
        except Exception as e:
            logger.warning(
                "从 KnowFlow 删除分享镜像失败 platform_doc=%s user=%s: %s",
                document.id,
                user.id,
                e,
            )
    db.delete(mirror)
    db.flush()
    return True


def remove_all_document_mirrors(db: Session, document: Document) -> int:
    removed = 0
    for mirror in list(
        db.scalars(
            select(RagflowDocumentMirrorLink).where(
                RagflowDocumentMirrorLink.platform_document_id == document.id
            )
        ).all()
    ):
        user = db.get(User, mirror.platform_user_id)
        if user and remove_document_mirror(db, document, user, commit_client=True):
            removed += 1
    return removed


def sync_shared_document_mirror(
    db: Session, user: User, document: Document, *, force: bool = False
) -> str | None:
    """将他人显式分享、可查询及以上的文档镜像到当前用户个人知识库。"""
    if not _should_mirror_shared_document(db, user, document):
        remove_document_mirror(db, document, user)
        return None

    canonical = _get_link(db, document.id)
    if not canonical or not canonical.ragflow_document_id:
        return None

    kf = get_knowflow_client_for_user(db, user)
    if not kf.enabled():
        return None

    target_ds = ensure_scope_dataset(
        db, user, SCOPE_PERSONAL, str(user.id), kf
    )
    if not target_ds:
        return None

    mirror = get_document_mirror_link(db, document.id, user.id)
    if mirror and not force and mirror.dataset_id == target_ds:
        return mirror.ragflow_document_id

    if mirror and force and mirror.ragflow_document_id and mirror.dataset_id:
        try:
            RagflowClient().delete_documents(
                mirror.dataset_id, [mirror.ragflow_document_id]
            )
        except Exception as e:
            logger.debug("强制重同步分享镜像前删除旧索引跳过: %s", e)

    version = resolve_current_version(db, document)
    if not version:
        return None

    from app.storage.object_store import get_object_store

    store = get_object_store()
    content = store.get_object_bytes(version.file_key)
    from app.integrations.html_document_export import normalize_file_for_knowflow_upload

    upload_name, upload_content, upload_mime = normalize_file_for_knowflow_upload(
        version.file_name,
        content,
        version.mime_type,
        title=document.title or "",
        description=document.description or "",
    )
    rag_doc_id = kf.sync_platform_document(
        platform_document_id=document.id,
        file_name=upload_name,
        content=upload_content,
        mime_type=upload_mime,
        dataset_id=target_ds,
    )
    if not rag_doc_id:
        return None

    if mirror:
        mirror.ragflow_document_id = rag_doc_id
        mirror.dataset_id = target_ds
        mirror.file_name = upload_name
    else:
        db.add(
            RagflowDocumentMirrorLink(
                platform_document_id=document.id,
                platform_user_id=user.id,
                ragflow_document_id=rag_doc_id,
                dataset_id=target_ds,
                file_name=upload_name,
            )
        )
    db.flush()
    return rag_doc_id


def sync_document_mirrors_for_shares(db: Session, document: Document) -> int:
    """按文档 ACL 同步/清理所有显式分享镜像（可查询及以上保留，以下删除）。"""
    from app.core.document_scope import can_query_document

    synced = 0
    user_ids = db.scalars(
        select(DocumentPermission.subject_id).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == "user",
        )
    ).all()
    seen: set[uuid.UUID] = set()
    for uid in user_ids:
        if uid in seen or uid == document.owner_id:
            continue
        seen.add(uid)
        user = db.get(User, uid)
        if not user or user.status != "active":
            continue
        if _should_mirror_shared_document(db, user, document):
            if sync_shared_document_mirror(db, user, document):
                synced += 1
        else:
            remove_document_mirror(db, document, user)
            if not can_query_document(db, user, document):
                from app.services.ragflow_scope_service import (
                    _ragflow_user_id,
                    revoke_kb_user_permission,
                )

                canonical = _get_link(db, document.id)
                rid = _ragflow_user_id(db, uid)
                if canonical and rid:
                    revoke_kb_user_permission(canonical.dataset_id, rid)
    return synced


def _delete_ragflow_documents_mysql(ragflow_doc_ids: list[str]) -> bool:
    if not ragflow_doc_ids:
        return False
    from app.integrations.ragflow_llm_template import _mysql_exec, _sql_literal

    ids = ",".join(f"'{_sql_literal(x)}'" for x in ragflow_doc_ids if x)
    if not ids:
        return False
    sql = f"""
DELETE FROM child_chunk WHERE doc_id IN ({ids});
DELETE FROM parent_chunk WHERE doc_id IN ({ids});
DELETE FROM file2document WHERE document_id IN ({ids});
DELETE FROM document WHERE id IN ({ids});
"""
    return _mysql_exec(sql)


def _ragflow_clients_for_document(db: Session, document: Document) -> list[RagflowClient]:
    from app.services.ragflow_scope_service import _privileged_rag_client

    clients: list[RagflowClient] = []
    seen: set[str] = set()

    def _add(client: RagflowClient | None) -> None:
        if client is None:
            return
        key = (client.session_auth or "") + "|" + (client.api_key or "")
        if key in seen:
            return
        seen.add(key)
        clients.append(client)

    _add(_privileged_rag_client(db))
    if document.owner_id:
        owner = db.get(User, document.owner_id)
        if owner:
            from app.services.ragflow_identity_service import get_user_ragflow_auth

            auth = get_user_ragflow_auth(db, owner)
            if auth:
                _add(RagflowClient(session_auth=auth))
    _add(RagflowClient())
    return clients


def remove_platform_document_from_knowflow(db: Session, document: Document) -> bool:
    """平台文档删除/关闭时，从 KnowFlow 知识库移除索引并删除映射。"""
    remove_all_document_mirrors(db, document)
    link = _get_link(db, document.id)
    if not link:
        return False
    deleted = False
    if link.dataset_id and link.ragflow_document_id:
        for client in _ragflow_clients_for_document(db, document):
            try:
                if client.health_ok():
                    client.delete_documents(
                        link.dataset_id, [link.ragflow_document_id]
                    )
                    deleted = True
                    break
            except Exception as e:
                logger.debug(
                    "KnowFlow 删除文档重试 platform_doc=%s: %s",
                    document.id,
                    e,
                )
        if not deleted:
            deleted = _delete_ragflow_documents_mysql([link.ragflow_document_id])
            if not deleted:
                logger.warning(
                    "从 KnowFlow 删除文档失败 platform_doc=%s",
                    document.id,
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

    if _should_mirror_shared_document(db, user, document):
        rid = sync_shared_document_mirror(db, user, document, force=force)
        if rid:
            sync_document_kb_grants(db, document)
        return rid

    provision_user, kf = _sync_context_for_document(db, user, document)
    if not kf.enabled():
        raise KnowflowSyncError(
            "知识服务未就绪，请先打开「切片管理」完成登录开户。"
        )

    target_ds = resolve_dataset_for_document(db, provision_user, document, kf)
    if not target_ds:
        from app.core.user_messages import KNOWLEDGE_SYNC_NO_KB

        raise KnowflowSyncError(KNOWLEDGE_SYNC_NO_KB)

    existing = _get_link(db, document.id)
    if existing and not force:
        if existing.dataset_id == target_ds:
            sync_document_kb_grants(db, document)
            return existing.ragflow_document_id
        force = True

    if existing and force and existing.ragflow_document_id and existing.dataset_id:
        try:
            RagflowClient().delete_documents(
                existing.dataset_id, [existing.ragflow_document_id]
            )
        except Exception as e:
            logger.debug("强制重同步前删除旧索引跳过: %s", e)

    version = resolve_current_version(db, document)
    if not version:
        from app.core.user_messages import KNOWLEDGE_SYNC_NO_FILE

        logger.warning("KnowFlow 同步跳过：无已上传版本 platform_doc=%s", document.id)
        raise KnowflowSyncError(KNOWLEDGE_SYNC_NO_FILE)

    from app.storage.object_store import get_object_store

    store = get_object_store()
    content = store.get_object_bytes(version.file_key)
    from app.integrations.html_document_export import normalize_file_for_knowflow_upload

    upload_name, upload_content, upload_mime = normalize_file_for_knowflow_upload(
        version.file_name,
        content,
        version.mime_type,
        title=document.title or "",
        description=document.description or "",
    )
    rag_doc_id = _upload_with_fallback(
        kf,
        dataset_id=target_ds,
        file_name=upload_name,
        content=upload_content,
        mime_type=upload_mime,
        platform_document_id=document.id,
        platform_user_id=provision_user.id,
    )
    if not rag_doc_id:
        from app.core.user_messages import KNOWLEDGE_SYNC_UPLOAD_FAILED

        raise KnowflowSyncError(KNOWLEDGE_SYNC_UPLOAD_FAILED)

    if existing:
        existing.ragflow_document_id = rag_doc_id
        existing.dataset_id = target_ds
        existing.platform_user_id = user.id
        existing.file_name = upload_name
    else:
        db.add(
            RagflowDocumentLink(
                platform_document_id=document.id,
                platform_user_id=user.id,
                ragflow_document_id=rag_doc_id,
                dataset_id=target_ds,
                file_name=upload_name,
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
    """将用户可查询的平台文档同步到 KnowFlow（含显式分享镜像）。"""
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
            if _should_mirror_shared_document(db, user, doc):
                mirror = get_document_mirror_link(db, doc.id, user.id)
                if mirror and mirror.ragflow_document_id:
                    try:
                        sync_document_kb_grants(db, doc)
                    except Exception as e:
                        logger.debug("刷新分享文档 KnowFlow 授权跳过 %s: %s", doc.id, e)
                elif limit > 0 and new_synced >= limit:
                    return mapping
                else:
                    rid = sync_shared_document_mirror(db, user, doc)
                    if rid:
                        mapping[str(doc.id)] = rid
                        new_synced += 1
                continue

            existing = _get_link(db, doc.id)
            if existing:
                try:
                    sync_document_kb_grants(db, doc)
                except Exception as e:
                    logger.debug("刷新 KnowFlow 授权跳过 %s: %s", doc.id, e)
                continue
            if limit > 0 and new_synced >= limit:
                return mapping
            try:
                rid = sync_document_to_knowflow(db, user, doc)
            except KnowflowSyncError as e:
                logger.warning("批量 KnowFlow 同步跳过 doc=%s: %s", doc.id, e.message)
                continue
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
        mirror = get_document_mirror_link(db, did, user.id)
        if mirror:
            out[pid] = mirror.ragflow_document_id
            continue
        link = _get_link(db, did)
        if link:
            out[pid] = link.ragflow_document_id
    return out
