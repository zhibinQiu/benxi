from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.content_checksum import compute_md5_hex, normalize_checksum
from app.core.document_upload_limits import (
    document_upload_max_bytes,
    document_upload_max_label,
)
from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store

logger = logging.getLogger(__name__)


def _try_sync_version_git(db: Session, version: DocumentVersion) -> None:
    try:
        from app.services.document_git_service import sync_version_to_git
        from app.services.document_version_block_service import ensure_version_blocks

        ensure_version_blocks(db, version)
        sync_version_to_git(db, version)
    except Exception:
        db.rollback()
        logger.warning(
            "版本 Git 同步失败 document=%s version=%s",
            version.document_id,
            version.id,
            exc_info=True,
        )


def get_document(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.get(Document, document_id)
def is_version_uploaded(version: DocumentVersion) -> bool:
    return bool(version.file_size and (version.file_key or "").strip())
def document_has_uploaded_version(db: Session, document_id: uuid.UUID) -> bool:
    row = db.scalar(
        select(DocumentVersion.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.file_size > 0,
        )
        .limit(1)
    )
    return row is not None
def create_initial_uploaded_version(
    db: Session,
    document: Document,
    user: User,
    *,
    file_name: str,
    mime_type: str,
    content: bytes,
    checksum: str | None = None,
    schedule_post_upload: bool = True,
) -> DocumentVersion:
    """创建并落库首版文件（用于导入、订阅等服务端直传场景）。"""
    store = get_object_store()
    mime = (mime_type or "application/octet-stream").strip()
    resolved_checksum = normalize_checksum(checksum) or compute_md5_hex(content)
    version = DocumentVersion(
        document_id=document.id,
        version_no=1,
        file_key=store.build_file_key(document.id, 1, file_name),
        file_name=file_name,
        mime_type=mime,
        file_size=len(content),
        checksum=resolved_checksum,
        created_by=user.id,
    )
    store.put_object_bytes(version.file_key, content, mime)
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    db.flush()
    db.refresh(version)
    db.refresh(document)
    if schedule_post_upload:
        from app.core.db_after_commit import run_after_commit
        from app.services.documents.post_upload import schedule_post_upload_processing

        run_after_commit(
            db,
            lambda: schedule_post_upload_processing(
                document.id, version.id, user.id
            ),
        )
    return version
def list_document_versions(db: Session, document_id: uuid.UUID) -> list[DocumentVersion]:
    rows = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
        ).all()
    )
    return [v for v in rows if is_version_uploaded(v)]


def get_baseline_uploaded_version(
    db: Session, document: Document
) -> DocumentVersion | None:
    """用于新版本格式校验：优先当前版本，否则取最早已上传版本。"""
    if document.current_version_id:
        cur = db.get(DocumentVersion, document.current_version_id)
        if cur and is_version_uploaded(cur):
            return cur
    return db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.file_size > 0,
        )
        .order_by(DocumentVersion.version_no.asc())
        .limit(1)
    )


def resolve_current_version(
    db: Session, document: Document, *, repair: bool = True
) -> DocumentVersion | None:
    """解析当前可下载版本；若库中 current_version_id 为空但已有上传文件则自动修复。"""
    versions = list_document_versions(db, document.id)
    if not versions:
        return None
    if document.current_version_id:
        current = db.get(DocumentVersion, document.current_version_id)
        if current and is_version_uploaded(current):
            return current
    pick_id = _pick_current_version_id(db, document, versions)
    if not pick_id:
        return None
    version = next((v for v in versions if v.id == pick_id), None)
    if version and repair and document.current_version_id != pick_id:
        document.current_version_id = pick_id
        db.flush()
    return version
def _pick_current_version_id(
    db: Session, document: Document, versions: list[DocumentVersion]
) -> uuid.UUID | None:
    if not versions:
        return None
    if document.current_version_id:
        cur = next((v for v in versions if v.id == document.current_version_id), None)
        if cur and is_version_uploaded(cur):
            return cur.id
    for v in versions:
        if is_version_uploaded(v):
            return v.id
    return versions[0].id
def delete_document_version(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    *,
    deleted_by: uuid.UUID,
) -> dict:
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import forbidden

    if not can_delete_document(db, user, document):
        raise forbidden("无权删除该版本")

    if version.document_id != document.id:
        from app.core.exceptions import not_found

        raise not_found("版本不存在")

    from app.services.documents.lifecycle import purge_version_knowledge_artifacts
    from app.services.ragflow_sync_service import schedule_knowflow_deletes

    knowflow_targets = purge_version_knowledge_artifacts(
        db, document, version, defer_knowflow=True
    )

    store = get_object_store()
    key = (version.file_key or "").strip()
    if key and is_version_uploaded(version):
        try:
            store.delete_object(key)
        except Exception:
            pass

    db.delete(version)
    db.flush()

    remaining = list_document_versions(db, document.id)
    if remaining:
        document.current_version_id = _pick_current_version_id(db, document, remaining)
        db.commit()
        schedule_knowflow_deletes(knowflow_targets)
        from app.core.platform_cache import invalidate_document_caches

        invalidate_document_caches(str(deleted_by))
        db.refresh(document)
        return {
            "ok": True,
            "document_deleted": False,
            "message": "版本已删除",
            "current_version_id": document.current_version_id,
        }

    document.current_version_id = None
    from app.services.documents.lifecycle import (
        purge_document_completely,
        schedule_documents_external_purge,
    )

    doc_id = document.id
    targets = purge_document_completely(
        db, document, defer_knowflow=True, skip_external=True
    )
    db.commit()
    schedule_documents_external_purge([doc_id])
    schedule_knowflow_deletes(knowflow_targets + targets)
    return {
        "ok": True,
        "document_deleted": True,
        "message": "已无版本，文档已删除",
        "current_version_id": None,
    }
def create_document(
    db: Session,
    user: User,
    *,
    title: str,
    description: str = "",
    scope: str = "personal",
    dept_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
) -> Document:
    from app.core.document_scope import resolve_create_params
    from app.services.library_folder_service import resolve_document_folder_id

    norm_scope, norm_dept = resolve_create_params(
        db, user, scope=scope, dept_id=dept_id
    )
    norm_folder_id = resolve_document_folder_id(
        db,
        user,
        scope=norm_scope,
        folder_id=folder_id,
        dept_id=norm_dept,
    )
    doc = Document(
        title=title,
        description=description,
        owner_id=user.id,
        dept_id=norm_dept,
        scope=norm_scope,
        folder_id=norm_folder_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return doc
def prepare_upload(
    db: Session,
    user: User,
    document: Document,
    *,
    file_name: str,
    mime_type: str,
) -> tuple[DocumentVersion, str]:
    if not can_access_document(db, user, document, PermissionLevel.modify.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to upload new version")

    from app.core.document_format import (
        assert_allowed_upload_format,
        assert_compatible_version_format,
    )

    assert_allowed_upload_format(file_name, mime_type)
    baseline = get_baseline_uploaded_version(db, document)
    if baseline:
        assert_compatible_version_format(
            existing_file_name=baseline.file_name,
            existing_mime=baseline.mime_type,
            new_file_name=file_name,
            new_mime=mime_type,
        )

    store = get_object_store()
    max_ver = db.scalar(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_id == document.id
        )
    )
    version_no = (max_ver or 0) + 1
    version = DocumentVersion(
        document_id=document.id,
        version_no=version_no,
        file_key=store.build_file_key(document.id, version_no, file_name),
        file_name=file_name,
        mime_type=mime_type,
        file_size=0,
        created_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    # 浏览器经平台 API 代理写入 MinIO（presigned 内网地址浏览器无法访问）
    upload_url = f"/api/v1/documents/{document.id}/upload/{version.id}/blob"
    return version, upload_url


def save_upload_blob(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    data: bytes,
    *,
    content_type: str | None = None,
) -> None:
    if version.document_id != document.id:
        from app.core.exceptions import not_found

        raise not_found("Version not found")
    if not can_access_document(db, user, document, PermissionLevel.modify.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to upload new version")
    if len(data) > document_upload_max_bytes():
        from app.core.exceptions import bad_request

        raise bad_request(f"单文件大小不能超过 {document_upload_max_label()}")
    from app.core.document_format import assert_allowed_upload_format

    assert_allowed_upload_format(
        version.file_name,
        content_type or version.mime_type,
    )
    mime = (content_type or version.mime_type or "application/octet-stream").strip()
    store = get_object_store()
    store.put_object_bytes(version.file_key, data, mime)
    version.file_size = len(data)
    version.checksum = compute_md5_hex(data)
    db.commit()


def complete_upload(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    *,
    file_size: int,
    checksum: str | None,
    change_description: str = "",
) -> Document:
    if not can_access_document(db, user, document, PermissionLevel.modify.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to complete upload")
    if file_size > document_upload_max_bytes():
        from app.core.exceptions import bad_request

        raise bad_request(f"单文件大小不能超过 {document_upload_max_label()}")

    from app.core.document_format import assert_compatible_version_format

    baseline = get_baseline_uploaded_version(db, document)
    if baseline and baseline.id != version.id:
        assert_compatible_version_format(
            existing_file_name=baseline.file_name,
            existing_mime=baseline.mime_type,
            new_file_name=version.file_name or "",
            new_mime=version.mime_type or "",
        )

    store = get_object_store()
    stored_size = store.head_object_size(version.file_key)
    if stored_size is None:
        from app.core.exceptions import bad_request

        raise bad_request(
            "文件尚未写入对象存储或已被清理，请重新上传后再完成。"
        )
    if stored_size != file_size:
        from app.core.exceptions import bad_request

        raise bad_request(
            f"上传文件大小不一致（声明 {file_size} 字节，存储 {stored_size} 字节），请重新上传。"
        )

    version.file_size = file_size
    if checksum:
        version.checksum = normalize_checksum(checksum)
    elif not version.checksum:
        content = store.get_object_bytes(version.file_key)
        version.checksum = compute_md5_hex(content)
    version.change_description = (change_description or "").strip()
    document.current_version_id = version.id
    db.commit()
    db.refresh(document)
    db.refresh(version)
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return document
def move_document_to_folder(
    db: Session,
    user: User,
    document: Document,
    *,
    folder_id: uuid.UUID | None,
) -> Document:
    from app.core.document_scope import VALID_SCOPES, can_modify_document
    from app.core.exceptions import bad_request, forbidden
    from app.services.library_folder_service import resolve_document_folder_id

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可移动")
    if not can_modify_document(db, user, document):
        raise forbidden("无权移动该文档")
    scope = (document.scope or "personal").strip()
    if scope not in VALID_SCOPES:
        raise bad_request("该文档分级不支持文件夹")

    norm_folder_id = resolve_document_folder_id(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        dept_id=document.dept_id,
    )
    document.folder_id = norm_folder_id
    db.commit()
    db.refresh(document)
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return document
def update_document(
    db: Session,
    user: User,
    document: Document,
    *,
    title: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    dept_id: uuid.UUID | None = None,
) -> Document:
    from app.core.document_scope import can_modify_document
    from app.core.exceptions import bad_request, forbidden

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可编辑")
    if scope is not None:
        publish_document_scope(db, user, document, scope=scope, dept_id=dept_id)
    if title is not None or description is not None:
        if not can_modify_document(db, user, document):
            raise forbidden("无权编辑该文档")
        if title is not None:
            t = title.strip()
            if not t:
                raise bad_request("标题不能为空")
            document.title = t[:512]
        if description is not None:
            document.description = description
    db.commit()
    db.refresh(document)
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return document


def publish_document_scope(
    db: Session,
    user: User,
    document: Document,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
) -> Document:
    """将文档发布到公司/部门/分部文库（改 scope，在对应 Tab 展示，不进「分享」）。"""
    from app.core.document_scope import (
        ORG_SCOPES,
        SCOPE_PERSONAL,
        resolve_create_params,
    )
    from app.core.exceptions import bad_request, forbidden
    from app.core.permissions import user_is_superuser

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可发布")
    if scope == SCOPE_PERSONAL:
        raise bad_request("请使用文档库「个人级」分级存放个人文档")
    if document.owner_id != user.id and not user_is_superuser(db, user):
        raise forbidden("仅文档创建人可发布到组织文库")
    norm_scope, norm_dept = resolve_create_params(db, user, scope=scope, dept_id=dept_id)
    document.scope = norm_scope
    document.dept_id = norm_dept if norm_scope in ORG_SCOPES else None
    document.folder_id = None
    db.flush()
    return document
def update_document_status(db: Session, document: Document, status: str) -> Document:
    from app.models.document import DocumentStatus

    allowed = {DocumentStatus.active.value, DocumentStatus.disabled.value}
    if status not in allowed:
        from app.core.exceptions import bad_request

        raise bad_request("状态仅支持 active（启用）或 disabled（关闭）")
    document.status = status
    if status == DocumentStatus.disabled.value:
        from app.services.ragflow_sync_service import remove_platform_document_from_knowflow

        remove_platform_document_from_knowflow(db, document)
    db.commit()
    db.refresh(document)
    return document
