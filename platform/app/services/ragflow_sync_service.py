"""平台文档 ↔ KnowFlow：按分级单库同步一份，权限由 RBAC 授权。"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass

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
    prepare_dataset_for_upload,
    resolve_dataset_for_document,
    sync_document_kb_grants,
)

logger = logging.getLogger(__name__)


class KnowflowSyncError(Exception):
    """文档同步 KnowFlow 失败（含用户可读原因）。"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _read_version_object_bytes(document: Document, version: DocumentVersion) -> bytes:
    from app.core.user_messages import STORAGE_FILE_MISSING
    from app.storage.object_store import StorageObjectNotFoundError, get_object_store

    store = get_object_store()
    try:
        return store.get_object_bytes(version.file_key)
    except StorageObjectNotFoundError as e:
        logger.warning(
            "KnowFlow 同步失败：MinIO 对象不存在 doc=%s key=%s",
            document.id,
            e.file_key,
        )
        raise KnowflowSyncError(STORAGE_FILE_MISSING) from e


def _sync_context_for_document(
    db: Session, actor: User, document: Document
) -> tuple[User, object]:
    """个人库文档须用所有者 KnowFlow 会话上传（permission=me）。"""
    scope = _document_scope(db, document)
    owner = db.get(User, document.owner_id) if document.owner_id else None
    if scope == SCOPE_PERSONAL and owner:
        return owner, get_knowflow_client_for_user(db, owner)
    return actor, get_knowflow_client_for_user(db, actor)


def _configure_and_parse_uploaded_document(
    kf,
    *,
    dataset_id: str,
    ragflow_document_id: str,
    file_name: str,
    mime_type: str,
    file_content: bytes | None = None,
    parser_id: str | None = None,
    layout_recognize: str | None = None,
) -> str | None:
    """上传后设置解析器并提交解析（覆盖 upload 时的默认 DeepDOC）。"""
    from app.integrations.ragflow_client import RagflowError
    from app.services.knowledge_parser_service import (
        build_parser_config,
        infer_parser_for_upload_file,
    )
    from app.services.ragflow_scope_service import _admin_rag_client

    if parser_id and layout_recognize:
        pid, layout = parser_id, layout_recognize
    else:
        pid, layout = infer_parser_for_upload_file(
            file_name, mime_type, file_content=file_content
        )
    parser, parser_config = build_parser_config(pid, layout)
    clients = [getattr(kf, "_rag", None)]
    admin = _admin_rag_client()
    if admin and admin not in clients:
        clients.append(admin)
    last_err: Exception | None = None
    for rag in clients:
        if rag is None:
            continue
        try:
            if rag.health_ok():
                rag.change_document_parser(
                    ragflow_document_id, parser, parser_config=parser_config
                )
                rag.parse_documents(dataset_id, [ragflow_document_id])
                return parser
        except RagflowError as e:
            last_err = e
            logger.warning(
                "KnowFlow 配置解析器失败 doc=%s parser=%s: %s",
                ragflow_document_id,
                parser,
                e,
            )
        except Exception as e:
            last_err = e
            logger.warning(
                "KnowFlow 提交解析失败 doc=%s: %s", ragflow_document_id, e
            )
    if last_err:
        logger.warning(
            "KnowFlow 未能为 doc=%s 应用解析器 %s: %s",
            ragflow_document_id,
            parser,
            last_err,
        )
    return parser


def _upload_rag_clients(
    db: Session,
    *,
    actor: User,
    document: Document,
    kf,
) -> list[RagflowClient]:
    """上传客户端顺序与分级库建库一致：mapped 下优先 bootstrap 特权会话。"""
    from app.services.ragflow_scope_service import (
        _admin_rag_client,
        _is_mapped_account_mode,
        _privileged_rag_client,
        _provision_rag_for_scope,
    )

    scope = _document_scope(db, document)
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

    if _is_mapped_account_mode():
        priv = _privileged_rag_client(db)
        admin = _admin_rag_client()
        if priv or admin:
            mapped_clients: list[RagflowClient] = []
            mapped_seen: set[str] = set()

            def _add_mapped(client: RagflowClient | None) -> None:
                if client is None:
                    return
                key = (client.session_auth or "") + "|" + (client.api_key or "")
                if key in mapped_seen:
                    return
                mapped_seen.add(key)
                mapped_clients.append(client)

            _add_mapped(priv)
            _add_mapped(admin)
            return mapped_clients

    _add(_provision_rag_for_scope(db, actor, scope, kf))
    _add(getattr(kf, "_rag", None))
    _add(_privileged_rag_client(db))
    _add(_admin_rag_client())
    return clients


def _upload_with_fallback(
    db: Session,
    actor: User,
    document: Document,
    kf,
    *,
    dataset_id: str,
    file_name: str,
    content: bytes,
    mime_type: str,
    platform_document_id: uuid.UUID,
    platform_user_id: uuid.UUID | None,
) -> str | None:
    clients = _upload_rag_clients(db, actor=actor, document=document, kf=kf)
    last_err: Exception | None = None
    for rag in clients:
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
                skip_auto_parse=True,
            )
            rag_doc_id = doc.get("id") or doc.get("doc_id")
            if rag_doc_id:
                return str(rag_doc_id), None
        except Exception as e:
            last_err = e
            logger.warning(
                "KnowFlow 上传重试 dataset=%s: %s",
                dataset_id,
                e,
            )
    if last_err:
        logger.warning("KnowFlow 上传全部失败 doc=%s: %s", platform_document_id, last_err)
    return None, _last_upload_error(last_err)


def _last_upload_error(err: Exception | None) -> str | None:
    if err is None:
        return None
    raw = str(err).strip()
    if "Unknown filter" in raw or "FOPN_foweb" in raw:
        return "PDF 使用了不支持的加密/压缩格式，请另存为标准 PDF 后再索引。"
    if "Tenant not found" in raw:
        return "知识库账号未就绪，请重新登录或联系管理员完成知识服务开户。"
    if "权限检查服务异常" in raw:
        return (
            "目标知识库在 KnowFlow 中不存在或权限服务异常，"
            "请打开「切片管理」同步知识库目录后重试。"
        )
    if "权限检查" in raw:
        return "知识库权限校验失败，请稍后重试或联系管理员。"
    from app.core.user_messages import sanitize_user_message

    msg = sanitize_user_message(raw, fallback="")
    return msg or None


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


@dataclass(frozen=True)
class KnowflowDeleteTarget:
    dataset_id: str
    ragflow_document_id: str


def _append_knowflow_target(
    targets: list[KnowflowDeleteTarget],
    seen: set[tuple[str, str]],
    dataset_id: str | None,
    ragflow_document_id: str | None,
) -> None:
    if not dataset_id or not ragflow_document_id:
        return
    key = (dataset_id, ragflow_document_id)
    if key in seen:
        return
    seen.add(key)
    targets.append(
        KnowflowDeleteTarget(
            dataset_id=dataset_id, ragflow_document_id=ragflow_document_id
        )
    )


def _execute_knowflow_deletes(
    db: Session,
    document: Document,
    targets: list[KnowflowDeleteTarget],
) -> None:
    for target in targets:
        deleted = False
        for client in _ragflow_clients_for_document(db, document):
            try:
                if client.health_ok():
                    client.delete_documents(
                        target.dataset_id, [target.ragflow_document_id]
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
            _delete_ragflow_documents_mysql([target.ragflow_document_id])


def schedule_knowflow_deletes(targets: list[KnowflowDeleteTarget]) -> None:
    """后台异步清理 KnowFlow 远端索引，避免批量删除阻塞请求。"""
    if not targets:
        return
    unique: dict[tuple[str, str], KnowflowDeleteTarget] = {}
    for target in targets:
        unique[(target.dataset_id, target.ragflow_document_id)] = target
    pending = list(unique.values())

    def run() -> None:
        client = RagflowClient()
        for target in pending:
            try:
                if client.health_ok():
                    client.delete_documents(
                        target.dataset_id, [target.ragflow_document_id]
                    )
                    continue
            except Exception as e:
                logger.debug("后台 KnowFlow 删除跳过: %s", e)
            _delete_ragflow_documents_mysql([target.ragflow_document_id])

    from app.core.background_executor import submit_background

    submit_background("knowflow-batch-delete", run)


def detach_platform_document_knowflow(
    db: Session,
    document: Document,
    *,
    sync_remote: bool = True,
) -> list[KnowflowDeleteTarget]:
    """删除本地 KnowFlow 映射；可选同步远端或返回待删目标供后台处理。"""
    from app.services.ragflow_version_link_service import (
        count_ragflow_document_references,
        list_version_links_for_document,
    )

    targets: list[KnowflowDeleteTarget] = []
    seen: set[tuple[str, str]] = set()
    preserved = 0

    def _maybe_append(ds_id: str | None, rag_id: str | None) -> None:
        nonlocal preserved
        if not ds_id or not rag_id:
            return
        if count_ragflow_document_references(
            db, rag_id, exclude_document_id=document.id
        ):
            preserved += 1
            logger.info(
                "保留共享 KnowFlow 索引 doc=%s rag=%s（其他文档仍引用）",
                document.id,
                rag_id,
            )
            return
        _append_knowflow_target(targets, seen, ds_id, rag_id)

    for mirror in list(
        db.scalars(
            select(RagflowDocumentMirrorLink).where(
                RagflowDocumentMirrorLink.platform_document_id == document.id
            )
        ).all()
    ):
        _maybe_append(mirror.dataset_id, mirror.ragflow_document_id)
        db.delete(mirror)

    for vl in list_version_links_for_document(db, document.id):
        _maybe_append(vl.dataset_id, vl.ragflow_document_id)
        db.delete(vl)

    link = _get_link(db, document.id)
    if link:
        _maybe_append(link.dataset_id, link.ragflow_document_id)
        db.delete(link)

    db.flush()
    if sync_remote and targets:
        _execute_knowflow_deletes(db, document, targets)
    if preserved:
        logger.info(
            "detach doc=%s 保留 %s 个共享 KnowFlow 索引",
            document.id,
            preserved,
        )
    return targets


def detach_platform_version_knowflow(
    db: Session,
    document: Document,
    version: DocumentVersion,
    *,
    sync_remote: bool = True,
) -> list[KnowflowDeleteTarget]:
    """删除版本级 KnowFlow 映射；无其他引用时清理远端 RAGFlow 文档与切片。"""
    from app.services.ragflow_version_link_service import (
        bind_document_to_indexed_version,
        count_ragflow_document_references,
        get_version_link_by_version_id,
        resolve_latest_indexed_version,
    )

    targets: list[KnowflowDeleteTarget] = []
    seen: set[tuple[str, str]] = set()
    vl = get_version_link_by_version_id(db, version.id)
    rag_id = (vl.ragflow_document_id if vl else "") or ""
    ds_id = (vl.dataset_id if vl else "") or ""

    doc_link = _get_link(db, document.id)
    if doc_link and rag_id and doc_link.ragflow_document_id == rag_id:
        latest = resolve_latest_indexed_version(db, document)
        if latest and latest.id != version.id:
            new_vl = get_version_link_by_version_id(db, latest.id)
            if new_vl:
                bind_document_to_indexed_version(
                    db,
                    document=document,
                    version=latest,
                    version_link=new_vl,
                )
            else:
                db.delete(doc_link)
        else:
            db.delete(doc_link)

    if vl:
        if ds_id and rag_id:
            if not count_ragflow_document_references(
                db, rag_id, exclude_document_id=document.id
            ):
                _append_knowflow_target(targets, seen, ds_id, rag_id)
        db.delete(vl)

    db.flush()
    if sync_remote and targets:
        _execute_knowflow_deletes(db, document, targets)
    return targets


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

    content = _read_version_object_bytes(document, version)
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
    targets = detach_platform_document_knowflow(db, document, sync_remote=True)
    return bool(targets)


def sync_document_to_knowflow(
    db: Session,
    user: User,
    document: Document,
    *,
    force: bool = False,
    version_id: uuid.UUID | None = None,
) -> str | None:
    """将文档同步到对应分级知识库（公司/部门/个人仅一份），并同步 KB 授权。"""
    from app.services.ragflow_version_link_service import (
        get_version_link_by_version_id,
        upsert_version_link,
    )

    if document.deleted_at is not None:
        return None
    if not can_access_document(db, user, document, PermissionLevel.query.value):
        return None

    if version_id is not None:
        force = True

    if _should_mirror_shared_document(db, user, document) and version_id is None:
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
    version_link = (
        get_version_link_by_version_id(db, version_id) if version_id else None
    )

    if version_id:
        version = db.get(DocumentVersion, version_id)
        if not version or version.document_id != document.id:
            from app.core.user_messages import KNOWLEDGE_SYNC_NO_FILE

            raise KnowflowSyncError(KNOWLEDGE_SYNC_NO_FILE)
    else:
        version = resolve_current_version(db, document)

    if not version:
        from app.core.user_messages import KNOWLEDGE_SYNC_NO_FILE

        logger.warning("KnowFlow 同步跳过：无已上传版本 platform_doc=%s", document.id)
        raise KnowflowSyncError(KNOWLEDGE_SYNC_NO_FILE)

    from app.services.document_checksum_service import ensure_version_checksum
    from app.services.ragflow_version_link_service import (
        find_reusable_knowflow_version_link,
        upsert_canonical_link,
    )

    content_checksum = ensure_version_checksum(db, version)
    if content_checksum:
        reusable = find_reusable_knowflow_version_link(
            db,
            dataset_id=target_ds,
            file_name=version.file_name,
            checksum=content_checksum,
            exclude_version_id=version.id,
        )
        reusable_id = (reusable.ragflow_document_id if reusable else "") or ""
        if reusable_id:
            vl = upsert_version_link(
                db,
                document=document,
                version=version,
                ragflow_document_id=reusable_id,
                dataset_id=target_ds,
                file_name=reusable.file_name or version.file_name,
                platform_user_id=provision_user.id,
                parser_id=reusable.parser_id,
            )
            if reusable.index_completed_at and vl.index_completed_at is None:
                vl.index_completed_at = reusable.index_completed_at
            upsert_canonical_link(
                db,
                document=document,
                ragflow_document_id=reusable_id,
                dataset_id=target_ds,
                file_name=vl.file_name,
                platform_user_id=provision_user.id,
            )
            db.flush()
            sync_document_kb_grants(db, document)
            source_doc = db.get(Document, reusable.platform_document_id)
            if source_doc and source_doc.id != document.id:
                sync_document_kb_grants(db, source_doc)
            logger.info(
                "KnowFlow 复用已有索引 doc=%s version=%s ragflow=%s source_doc=%s",
                document.id,
                version.id,
                reusable_id,
                reusable.platform_document_id,
            )
            return reusable_id

    if existing and not force:
        if existing.dataset_id == target_ds:
            sync_document_kb_grants(db, document)
            return existing.ragflow_document_id
        force = True

    if force:
        stale_ids: list[tuple[str, str]] = []
        if version_link and version_link.ragflow_document_id and version_link.dataset_id:
            stale_ids.append(
                (version_link.dataset_id, version_link.ragflow_document_id)
            )
        elif (
            existing
            and existing.ragflow_document_id
            and existing.dataset_id
            and version_id is None
        ):
            stale_ids.append((existing.dataset_id, existing.ragflow_document_id))
        reuse_ids: set[str] = set()
        if content_checksum:
            reuse = find_reusable_knowflow_version_link(
                db,
                dataset_id=target_ds,
                file_name=version.file_name,
                checksum=content_checksum,
                exclude_version_id=version.id,
            )
            rid = (reuse.ragflow_document_id if reuse else "") or ""
            if rid:
                reuse_ids.add(rid)
        for ds_id, rag_id in stale_ids:
            if rag_id in reuse_ids:
                continue
            try:
                RagflowClient().delete_documents(ds_id, [rag_id])
            except Exception as e:
                logger.debug("强制重同步前删除旧索引跳过: %s", e)

    from app.services.document_version_block_service import (
        resolve_knowflow_upload_from_version,
    )

    upload_name, upload_content, upload_mime, _from_blocks = (
        resolve_knowflow_upload_from_version(
            db,
            document,
            version,
            read_object_bytes=_read_version_object_bytes,
        )
    )
    prepare_dataset_for_upload(
        db,
        document,
        target_ds,
        actor=user,
        provision_user=provision_user,
    )
    rag_doc_id, upload_err = _upload_with_fallback(
        db,
        provision_user,
        document,
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

        raise KnowflowSyncError(upload_err or KNOWLEDGE_SYNC_UPLOAD_FAILED)

    applied_parser = _configure_and_parse_uploaded_document(
        kf,
        dataset_id=target_ds,
        ragflow_document_id=rag_doc_id,
        file_name=upload_name,
        mime_type=upload_mime,
        file_content=upload_content,
    )

    upsert_version_link(
        db,
        document=document,
        version=version,
        ragflow_document_id=rag_doc_id,
        dataset_id=target_ds,
        file_name=upload_name,
        platform_user_id=provision_user.id,
        parser_id=applied_parser,
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
            except Exception as e:
                from app.storage.object_store import StorageObjectNotFoundError

                if isinstance(e, StorageObjectNotFoundError):
                    logger.warning(
                        "批量 KnowFlow 同步跳过 doc=%s: MinIO 对象不存在 key=%s",
                        doc.id,
                        e.file_key,
                    )
                    continue
                raise
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
    """平台文档 ID → RAGFlow 文档 ID（最后索引成功版本的切片，可查询权限）。"""
    from app.services.ragflow_version_link_service import resolve_index_link

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
        vl, _version = resolve_index_link(db, doc)
        if vl and vl.ragflow_document_id:
            out[pid] = vl.ragflow_document_id
            continue
        link = _get_link(db, did)
        if link:
            out[pid] = link.ragflow_document_id
    return out
