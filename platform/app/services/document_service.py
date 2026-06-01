from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.storage.object_store import get_object_store


def _user_share_meta(
    db: Session, user: User, document: Document
) -> dict[str, str | None]:
    """当前用户对该文档的显式用户级授权元数据。"""
    from datetime import datetime, timezone

    from app.core.permissions import level_order

    now = datetime.now(timezone.utc)
    perms = list(
        db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id,
                DocumentPermission.subject_type == "user",
                DocumentPermission.subject_id == user.id,
            )
        ).all()
    )
    best_level: str | None = None
    granted_by: uuid.UUID | None = None
    for perm in perms:
        if perm.expires_at and perm.expires_at < now:
            continue
        if best_level is None or level_order(perm.level) > level_order(best_level):
            best_level = perm.level
            granted_by = perm.granted_by
    granted_by_name: str | None = None
    if granted_by:
        granter = db.get(User, granted_by)
        if granter:
            granted_by_name = (
                f"{granter.username} · {granter.display_name}"
                if granter.display_name
                else granter.username
            )
    return {"shared_level": best_level, "granted_by_name": granted_by_name}


def list_shared_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, dict[str, str | None]]], int]:
    """他人通过显式授权分享的文档（不含仅靠部门/公司默认可见的文档）。"""
    from app.core.document_scope import (
        _has_explicit_permission,
        can_read_document,
        readable_by_scope_default,
    )
    from app.core.permissions import PermissionLevel

    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.owner_id != user.id,
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible: list[tuple[Document, dict[str, str | None]]] = []
    for doc in candidates:
        if not document_has_uploaded_version(db, doc.id):
            continue
        if not _has_explicit_permission(
            db, user, doc, PermissionLevel.visible.value
        ):
            continue
        if not can_read_document(db, user, doc):
            continue
        if readable_by_scope_default(db, user, doc):
            continue
        visible.append((doc, _user_share_meta(db, user, doc)))
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


def list_accessible_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
    scope: str | None = None,
    min_permission_level: str | None = None,
    folder_id: uuid.UUID | None = None,
    uncategorized_only: bool = False,
) -> tuple[list[Document], int]:
    from app.core.document_scope import VALID_SCOPES
    from app.models.document import DocumentStatus

    required = min_permission_level or PermissionLevel.visible.value
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if scope:
        if scope not in VALID_SCOPES:
            from app.core.exceptions import bad_request

            raise bad_request("无效的分级 scope")
        stmt = stmt.where(Document.scope == scope)
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    if uncategorized_only:
        stmt = stmt.where(Document.folder_id.is_(None))
    elif folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    from app.core.document_scope import owner_qualifies_for_scope_list

    from app.core.permissions import user_is_superuser

    is_super = user_is_superuser(db, user)
    visible: list[Document] = []
    for d in candidates:
        if not document_has_uploaded_version(db, d.id):
            continue
        if not can_access_document(db, user, d, required):
            continue
        doc_scope = d.scope or "personal"
        if scope == "personal" and d.owner_id != user.id and not is_super:
            continue
        if (
            not is_super
            and doc_scope == "company"
            and not owner_qualifies_for_scope_list(db, d)
        ):
            continue
        if (
            not is_super
            and doc_scope == "department"
            and not owner_qualifies_for_scope_list(db, d)
        ):
            continue
        visible.append(d)
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


def list_all_visible_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    """跨分级汇总：当前用户具备「可见」及以上权限的全部文档（不做分级入库员过滤）。"""
    from app.models.document import DocumentStatus

    required = PermissionLevel.visible.value
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible: list[Document] = []
    for doc in candidates:
        if not document_has_uploaded_version(db, doc.id):
            continue
        if not can_access_document(db, user, doc, required):
            continue
        visible.append(doc)
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


def list_queryable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    """当前用户具备「可查询」及以上权限的全部启用文档（跨分级，含管理员可见范围）。"""
    from app.core.document_scope import can_query_document
    from app.models.document import DocumentStatus

    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible: list[Document] = []
    for doc in candidates:
        if doc.deleted_at is not None:
            continue
        if not document_has_uploaded_version(db, doc.id):
            continue
        if not can_query_document(db, user, doc):
            continue
        visible.append(doc)
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


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
) -> DocumentVersion:
    """创建并落库首版文件（用于导入、订阅等服务端直传场景）。"""
    store = get_object_store()
    version = DocumentVersion(
        document_id=document.id,
        version_no=1,
        file_key=store.build_file_key(document.id, 1, file_name),
        file_name=file_name,
        mime_type=mime_type or "application/octet-stream",
        file_size=len(content),
        checksum=checksum,
        created_by=user.id,
    )
    store.put_object_bytes(version.file_key, content, mime_type)
    db.add(version)
    document.current_version_id = version.id
    db.commit()
    db.refresh(version)
    db.refresh(document)
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
        db.refresh(document)
        return {
            "ok": True,
            "document_deleted": False,
            "message": "版本已删除",
            "current_version_id": document.current_version_id,
        }

    document.current_version_id = None
    soft_delete_document(db, document, deleted_by=deleted_by)
    return {
        "ok": True,
        "document_deleted": True,
        "message": "已无版本，文档已移入回收站",
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
    return doc


def prepare_upload(
    db: Session,
    user: User,
    document: Document,
    *,
    file_name: str,
    mime_type: str,
) -> tuple[DocumentVersion, str]:
    if not can_access_document(db, user, document, PermissionLevel.edit.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to upload new version")

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
    upload_url = store.presigned_put(version.file_key, mime_type)
    return version, upload_url


def complete_upload(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion,
    *,
    file_size: int,
    checksum: str | None,
) -> Document:
    if not can_access_document(db, user, document, PermissionLevel.edit.value):
        from app.core.exceptions import forbidden

        raise forbidden("No permission to complete upload")

    version.file_size = file_size
    version.checksum = checksum
    document.current_version_id = version.id
    db.commit()
    db.refresh(document)
    return document


def grant_permission(
    db: Session,
    user: User,
    document: Document,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    level: str,
    expires_at,
) -> DocumentPermission:
    from app.core.document_scope import can_grant_document_permissions

    if not can_grant_document_permissions(db, user, document):
        from app.core.exceptions import forbidden

        raise forbidden("仅文档创建人或系统管理员可授权")

    from app.core.permissions import LEVEL_ORDER, normalize_permission_level
    from app.core.exceptions import bad_request

    norm = normalize_permission_level(level)
    if norm not in LEVEL_ORDER:
        raise bad_request(
            "无效的授权级别，可选：visible、query、edit、full"
        )

    perm = DocumentPermission(
        document_id=document.id,
        subject_type=subject_type,
        subject_id=subject_id,
        level=norm,
        granted_by=user.id,
        expires_at=expires_at,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def list_acl_user_candidates(db: Session, document: Document) -> list[dict]:
    """授权/禁止访问时可选的用户列表（不含文档创建人）。"""
    from app.core.document_scope import SCOPE_COMPANY, SCOPE_DEPARTMENT
    from app.core.permissions import user_has_permission
    from app.models.org import Department, User, UserDepartment

    stmt = select(User).where(User.status == "active", User.id != document.owner_id)
    if document.scope == SCOPE_DEPARTMENT and document.dept_id:
        stmt = stmt.join(
            UserDepartment, UserDepartment.user_id == User.id
        ).where(UserDepartment.dept_id == document.dept_id)
    users = list(db.scalars(stmt.order_by(User.display_name, User.username).limit(500)).all())
    if document.scope == SCOPE_COMPANY:
        users = [u for u in users if user_has_permission(db, u, "doc.read")]
    if not users:
        return []

    user_ids = [u.id for u in users]
    dept_rows = db.execute(
        select(UserDepartment.user_id, Department.name)
        .join(Department, Department.id == UserDepartment.dept_id)
        .where(UserDepartment.user_id.in_(user_ids))
    ).all()
    dept_map: dict[uuid.UUID, list[str]] = {}
    for uid, name in dept_rows:
        dept_map.setdefault(uid, []).append(name)

    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name or u.username,
            "department_names": dept_map.get(u.id, []),
        }
        for u in users
    ]


def list_document_permissions(
    db: Session, document_id: uuid.UUID
) -> list[DocumentPermission]:
    return list(
        db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document_id
            )
        ).all()
    )


def revoke_permission(
    db: Session, actor: User, document: Document, perm_id: uuid.UUID
) -> None:
    from app.core.document_scope import can_grant_document_permissions
    from app.core.exceptions import forbidden

    if not can_grant_document_permissions(db, actor, document):
        raise forbidden("仅文档创建人或系统管理员可撤销授权")
    perm = db.get(DocumentPermission, perm_id)
    if not perm or perm.document_id != document.id:
        from app.core.exceptions import not_found

        raise not_found("授权记录不存在")
    db.delete(perm)
    db.commit()


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
    from app.models.job import Job, JobEvent, JobType

    doc_str = str(document_id)
    job_ids: set[uuid.UUID] = set(
        db.scalars(select(Job.id).where(Job.document_id == document_id)).all()
    )
    for job in db.scalars(
        select(Job).where(Job.type == JobType.pdf_translate.value)
    ).all():
        if (job.payload or {}).get("document_id") == doc_str:
            job_ids.add(job.id)
    if not job_ids:
        return
    db.execute(delete(JobEvent).where(JobEvent.job_id.in_(job_ids)))
    db.execute(delete(Job).where(Job.id.in_(job_ids)))


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
    _purge_document_storage(db, document)
    db.execute(
        delete(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == doc_id
        )
    )
    # 先解除 current_version 引用，再删版本，避免 ORM 将 document_id 置空
    document.current_version_id = None
    db.flush()
    db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == doc_id))
    db.delete(document)
    db.flush()


def permanently_delete_document(
    db: Session, user: User, document: Document
) -> None:
    from app.core.document_scope import can_delete_document
    from app.core.exceptions import bad_request, forbidden

    if document.deleted_at is None:
        if not can_delete_document(db, user, document):
            raise forbidden("无权删除该文档")
    elif not can_permanently_delete_document(db, user, document):
        raise forbidden("无权彻底删除该文档")

    purge_document_completely(db, document)
    db.commit()


def empty_recycle_bin(db: Session, user: User) -> int:
    """彻底删除当前用户回收站中的全部文档。"""
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


def move_document_to_folder(
    db: Session,
    user: User,
    document: Document,
    *,
    folder_id: uuid.UUID | None,
) -> Document:
    from app.core.document_scope import VALID_SCOPES, can_edit_document
    from app.core.exceptions import bad_request, forbidden
    from app.services.library_folder_service import resolve_document_folder_id

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可移动")
    if not can_edit_document(db, user, document):
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
    return document


def update_document(
    db: Session,
    user: User,
    document: Document,
    *,
    title: str | None = None,
    description: str | None = None,
) -> Document:
    from app.core.document_scope import can_edit_document
    from app.core.exceptions import bad_request, forbidden

    if document.deleted_at is not None:
        raise bad_request("回收站中的文档不可编辑")
    if not can_edit_document(db, user, document):
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


def _subject_user_label(db: Session, user_id: uuid.UUID) -> str:
    u = db.get(User, user_id)
    if not u:
        return "未知用户"
    return u.username or "未知用户"


def list_my_shared_out_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, dict[str, str | int | None]]], int]:
    """我作为上传人/授权人分享给他人的文档。"""
    from datetime import datetime, timezone

    from app.core.permissions import LEVEL_LABELS, level_order

    now = datetime.now(timezone.utc)
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.owner_id == user.id,
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    visible: list[tuple[Document, dict]] = []
    for doc in candidates:
        if not document_has_uploaded_version(db, doc.id):
            continue
        perms = list(
            db.scalars(
                select(DocumentPermission).where(
                    DocumentPermission.document_id == doc.id,
                    DocumentPermission.subject_type == "user",
                    DocumentPermission.subject_id != user.id,
                )
            ).all()
        )
        active = [p for p in perms if not p.expires_at or p.expires_at >= now]
        if not active:
            continue
        parts: list[str] = []
        for p in sorted(active, key=lambda x: level_order(x.level), reverse=True):
            label = LEVEL_LABELS.get(p.level, p.level)
            parts.append(f"{_subject_user_label(db, p.subject_id)}（{label}）")
        visible.append(
            (
                doc,
                {
                    "share_count": len(active),
                    "share_to_summary": "、".join(parts),
                },
            )
        )
    total = len(visible)
    start = (page - 1) * page_size
    return visible[start : start + page_size], total


def list_recycle_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    from sqlalchemy import and_

    stmt = select(Document).where(
        and_(
            Document.deleted_at.is_not(None),
            Document.deleted_by == user.id,
        )
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(
        db.scalars(stmt.order_by(Document.deleted_at.desc())).all()
    )
    total = len(candidates)
    start = (page - 1) * page_size
    return candidates[start : start + page_size], total


def _is_compareable_version(version: DocumentVersion) -> bool:
    name = (version.file_name or "").lower()
    mime = (version.mime_type or "").lower()
    if name.endswith(".pdf") or mime == "application/pdf":
        return True
    if name.endswith((".doc", ".docx")) or "word" in mime:
        return True
    return False


def _is_pdf_version(version: DocumentVersion) -> bool:
    mime = (version.mime_type or "").lower()
    if "pdf" in mime:
        return True
    return (version.file_name or "").lower().endswith(".pdf")


def _list_documents_with_current_version(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    required_level: str,
    version_ok,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """未删除、已启用、当前版本已上传，且用户具备 required_level（通常为可查询）。"""
    from app.core.document_scope import can_query_document
    from app.core.permissions import PermissionLevel
    from app.models.document import DocumentStatus

    cur_ver = DocumentVersion.__table__.alias("cur_ver")
    stmt = (
        select(Document)
        .join(cur_ver, Document.current_version_id == cur_ver.c.id)
        .where(
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.active.value,
            Document.current_version_id.is_not(None),
            cur_ver.c.file_size > 0,
        )
    )
    if keyword:
        stmt = stmt.where(Document.title.ilike(f"%{keyword}%"))
    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    rows: list[tuple[Document, DocumentVersion]] = []
    query_level = (
        required_level
        if required_level == PermissionLevel.query.value
        else required_level
    )
    for doc in candidates:
        if doc.deleted_at is not None:
            continue
        if doc.status != DocumentStatus.active.value:
            continue
        if query_level == PermissionLevel.query.value:
            if not can_query_document(db, user, doc):
                continue
        elif not can_access_document(db, user, doc, required_level):
            continue
        version = db.get(DocumentVersion, doc.current_version_id)
        if not version or not is_version_uploaded(version) or not version_ok(version):
            continue
        rows.append((doc, version))
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total


def list_translatable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """当前用户有「可查询」及以上权限、已上传 PDF 当前版本的文档。"""
    return _list_documents_with_current_version(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        required_level=PermissionLevel.query.value,
        version_ok=_is_pdf_version,
    )


def list_compareable_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Document, DocumentVersion]], int]:
    """当前用户有「可查询」及以上权限、可对比格式的当前版本文档。"""
    return _list_documents_with_current_version(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        required_level=PermissionLevel.query.value,
        version_ok=_is_compareable_version,
    )


def read_document_pdf_bytes(
    db: Session, user: User, document_id: uuid.UUID
) -> tuple[bytes, str, Document]:
    """读取文档当前版本 PDF 内容；校验「可查询」权限（翻译/对比/检索）。"""
    from app.core.exceptions import bad_request, forbidden, not_found
    from app.models.document import DocumentStatus

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    if doc.status != DocumentStatus.active.value:
        raise bad_request("文档已关闭或不可用")
    if not can_access_document(db, user, doc, PermissionLevel.query.value):
        raise forbidden("无权查询或使用该文档")
    if not doc.current_version_id:
        raise bad_request("文档尚未上传文件")
    version = db.get(DocumentVersion, doc.current_version_id)
    if not version:
        raise bad_request("文档版本不存在")
    if not _is_pdf_version(version):
        raise bad_request("仅支持 PDF 文档翻译")
    data = get_object_store().get_object_bytes(version.file_key)
    return data, version.file_name, doc


def get_download_url(
    db: Session, user: User, document: Document
) -> str | None:
    if not can_access_document(db, user, document, PermissionLevel.visible.value):
        return None
    if not document.current_version_id:
        return None
    version = db.get(DocumentVersion, document.current_version_id)
    if not version or not is_version_uploaded(version):
        return None
    return get_object_store().presigned_get(version.file_key)
