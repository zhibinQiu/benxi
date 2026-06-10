from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.core.document_format import version_file_format_label
from app.core.document_scope import (
    can_delete_document,
    can_edit_document,
    can_grant_document_permissions,
    can_manage_document,
    can_manage_document_acl,
    can_manage_document_denials,
    can_query_document,
    can_read_document,
    can_restore_document,
    effective_permission_level,
)
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import PermissionLevel, can_access_document
from app.database import get_db
from app.models.document import Document, DocumentLibraryFolder, DocumentVersion
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.models.org import Department
from app.schemas.document import (
    DocumentCreate,
    DocumentDetail,
    DocumentFolderOut,
    DocumentLibraryOut,
    DocumentGrant,
    DocumentListItem,
    AclPickerOut,
    DocumentAccessControlOut,
    DocumentPermissionOut,
    DocumentShareOut,
    DocumentShareBatchIn,
    DocumentStatusUpdate,
    DocumentUpdate,
    DocumentMoveIn,
    DocumentBatchDeleteIn,
    DocumentBatchDeleteOut,
    DeleteDocumentVersionResult,
    DocumentVersionOut,
    DocumentUploadCompleteOut,
    UploadCompleteRequest,
    UploadPrepareResponse,
    DocumentKnowflowSyncOut,
    KbFolderCreate,
    KbFolderListOut,
    KbFolderOut,
    KbFolderUpdate,
)
from app.services import library_folder_service
from app.schemas.document_workflow import DocumentDenialCreate, DocumentDenialOut
from app.services import document_workflow_service
from app.core.document_scope import library_folders
from app.core.document_scope import (
    library_companies_for_user,
    library_departments_for_user,
    library_teams_for_user,
)
from app.core.permissions import user_dept_ids, user_is_superuser
from app.config import get_settings
from app.core.document_upload_limits import document_upload_max_label
from app.domains.knowledge import knowledge
from app.services import audit_service, document_service, job_service

router = APIRouter(prefix="/documents", tags=["documents"])


def _sync_kb_grants_if_enabled(db: Session, doc: Document) -> None:
    if not get_settings().knowflow_enabled:
        return
    try:
        knowledge.sync_kb_grants(db, doc)
    except Exception:
        pass


def _owner_display(db: Session, owner_id: uuid.UUID) -> str:
    from app.core.user_display import user_display_name

    return user_display_name(db.get(User, owner_id))


def _dept_display(db: Session, dept_id: uuid.UUID | None) -> str | None:
    if not dept_id:
        return None
    from app.models.org import Department

    dept = db.get(Department, dept_id)
    if not dept:
        return None
    return (dept.name or "").strip() or None


def _uploaded_at(db: Session, doc: Document) -> datetime | None:
    if doc.current_version_id:
        ver = db.get(DocumentVersion, doc.current_version_id)
        if ver:
            return ver.created_at
    first = db.scalar(
        select(DocumentVersion.created_at)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_no.asc())
        .limit(1)
    )
    return first or doc.created_at


def _version_out(
    db: Session,
    doc: Document,
    version: DocumentVersion,
    *,
    user: User | None = None,
    index_meta: dict | None = None,
) -> DocumentVersionOut:
    from app.services.document_index_service import apply_index_meta_to_item

    uploaded = document_service.is_version_uploaded(version)
    base = DocumentVersionOut.model_validate(version)
    row = base.model_copy(
        update={
            "uploaded": uploaded,
            "is_current": version.id == doc.current_version_id,
            "file_name": version.file_name or "",
        }
    )
    if user is not None and index_meta is not None:
        row = apply_index_meta_to_item(row, index_meta.get(str(version.id)))
    return row


def _folder_name(db: Session, folder_id: uuid.UUID | None) -> str | None:
    if not folder_id:
        return None
    folder = db.get(DocumentLibraryFolder, folder_id)
    return (folder.name or "").strip() or None if folder else None


def _detail(db: Session, doc: Document, *, user: User | None = None) -> DocumentDetail:
    from app.services.document_index_service import (
        apply_index_meta_to_item,
        enrich_document_index_meta,
    )

    document_service.resolve_current_version(db, doc)
    db.refresh(doc)
    from app.services.document_index_service import enrich_version_index_meta

    can_edit = can_edit_document(db, user, doc) if user else False
    version_rows = document_service.list_document_versions(db, doc.id)
    version_meta = (
        enrich_version_index_meta(db, user, version_rows) if user else {}
    )
    detail = DocumentDetail(
        id=doc.id,
        title=doc.title,
        status=doc.status,
        scope=doc.scope,
        folder_id=doc.folder_id,
        folder_name=_folder_name(db, doc.folder_id),
        owner_id=doc.owner_id,
        owner_name=_owner_display(db, doc.owner_id),
        dept_id=doc.dept_id,
        dept_name=_dept_display(db, doc.dept_id),
        current_version_id=doc.current_version_id,
        description=doc.description,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        uploaded_at=_uploaded_at(db, doc),
        deleted_at=doc.deleted_at,
        can_edit=can_edit,
        versions=[
            _version_out(db, doc, v, user=user, index_meta=version_meta)
            for v in version_rows
        ],
    )
    if user is not None:
        meta = enrich_document_index_meta(db, user, [doc]).get(str(doc.id))
        detail = apply_index_meta_to_item(detail, meta)
    return detail


@router.get("/kb-folders", response_model=ApiResponse[KbFolderListOut])
def list_kb_folders(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    scope: str = Query(..., pattern="^(company|department|team|personal)$"),
    dept_id: uuid.UUID | None = None,
) -> ApiResponse[KbFolderListOut]:
    data = library_folder_service.list_kb_folders(
        db, user, scope=scope, dept_id=dept_id
    )
    return ApiResponse(
        data=KbFolderListOut(
            scope=data["scope"],
            dept_id=data["dept_id"],
            can_manage_folders=data["can_manage_folders"],
            items=[KbFolderOut.model_validate(i) for i in data["items"]],
        )
    )


@router.post("/kb-folders", response_model=ApiResponse[KbFolderOut])
def create_kb_folder(
    body: KbFolderCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KbFolderOut]:
    folder = library_folder_service.create_kb_folder(
        db,
        user,
        name=body.name,
        description=body.description,
        scope=body.scope,
        dept_id=body.dept_id,
    )
    db.commit()
    return ApiResponse(
        data=KbFolderOut(
            id=folder.id,
            name=folder.name,
            description=folder.description or "",
            scope=folder.scope,
            dept_id=folder.dept_id,
            kind="normal",
            is_system=False,
            document_count=0,
            can_manage=True,
        )
    )


@router.patch("/kb-folders/{folder_id}", response_model=ApiResponse[KbFolderOut])
def update_kb_folder(
    folder_id: uuid.UUID,
    body: KbFolderUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KbFolderOut]:
    folder = library_folder_service.update_kb_folder(
        db,
        user,
        folder_id,
        name=body.name,
        description=body.description,
    )
    db.commit()
    return ApiResponse(
        data=KbFolderOut(
            id=folder.id,
            name=folder.name,
            description=folder.description or "",
            scope=folder.scope,
            dept_id=folder.dept_id,
            kind="normal",
            is_system=False,
            document_count=0,
            can_manage=True,
        )
    )


@router.delete("/kb-folders/{folder_id}", response_model=ApiResponse[dict])
def delete_kb_folder(
    folder_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    library_folder_service.delete_kb_folder(db, user, folder_id)
    db.commit()
    return ApiResponse(data={"ok": True})


@router.get("/library", response_model=ApiResponse[DocumentLibraryOut])
def document_library(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentLibraryOut]:
    folders = library_folders(db, user)
    dept_rows = [
        {"id": str(d["id"]), "name": d["name"]}
        for d in library_departments_for_user(db, user)
    ]
    team_rows = [
        {"id": str(d["id"]), "name": d["name"]}
        for d in library_teams_for_user(db, user)
    ]
    company_rows = [
        {"id": str(d["id"]), "name": d["name"]}
        for d in library_companies_for_user(db, user)
    ]
    return ApiResponse(
        data=DocumentLibraryOut(
            folders=[DocumentFolderOut.model_validate(f) for f in folders],
            companies=company_rows,
            departments=dept_rows,
            teams=team_rows,
            upload_max_file_mb=get_settings().document_upload_max_file_mb,
            upload_max_size_label=document_upload_max_label(),
        )
    )


def _attach_folder_names(
    db: Session, items: list[DocumentListItem]
) -> list[DocumentListItem]:
    folder_ids = {i.folder_id for i in items if i.folder_id}
    names: dict[uuid.UUID, str] = {}
    if folder_ids:
        for row in db.scalars(
            select(DocumentLibraryFolder).where(
                DocumentLibraryFolder.id.in_(folder_ids)
            )
        ).all():
            names[row.id] = row.name
    return [
        item.model_copy(
            update={"folder_name": names.get(item.folder_id) if item.folder_id else None}
        )
        for item in items
    ]


def _current_version_formats(
    db: Session, docs: list[Document]
) -> dict[uuid.UUID, str | None]:
    version_ids = [d.current_version_id for d in docs if d.current_version_id]
    if not version_ids:
        return {}
    rows = db.scalars(
        select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
    ).all()
    return {
        v.id: version_file_format_label(v.file_name, v.mime_type) for v in rows
    }


def _list_items_with_owners(
    db: Session,
    docs: list[Document],
    *,
    include_owner_name: bool,
    user: User | None = None,
) -> list[DocumentListItem]:
    from app.core.document_scope import can_edit_document
    from app.services.document_index_service import (
        apply_index_meta_to_item,
        enrich_document_index_meta,
    )

    fmt_by_ver = _current_version_formats(db, docs)
    index_meta = enrich_document_index_meta(db, user, docs) if user else {}
    out: list[DocumentListItem] = []
    for d in docs:
        item = DocumentListItem.model_validate(d)
        extra: dict = {"uploaded_at": _uploaded_at(db, d)}
        if d.current_version_id and d.current_version_id in fmt_by_ver:
            extra["file_format"] = fmt_by_ver[d.current_version_id]
        if include_owner_name:
            extra["owner_name"] = _owner_display(db, d.owner_id)
        if d.dept_id:
            extra["dept_name"] = _dept_display(db, d.dept_id)
        if user is not None:
            extra["can_edit"] = can_edit_document(db, user, d)
            extra["can_delete"] = can_delete_document(db, user, d)
        item = item.model_copy(update=extra)
        if user is not None:
            item = apply_index_meta_to_item(item, index_meta.get(str(d.id)))
        out.append(item)
    return out


@router.get("", response_model=ApiResponse[PageResult[DocumentListItem]])
def list_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    scope: str | None = Query(
        None, pattern="^(company|department|team|personal|shared|all)$"
    ),
    folder_id: uuid.UUID | None = None,
    uncategorized: bool = Query(False, description="仅未归入文件夹的文档"),
    dept_id: uuid.UUID | None = None,
) -> ApiResponse[PageResult[DocumentListItem]]:
    if scope in ("company", "department", "team") and dept_id is not None:
        from app.core.document_scope import user_can_access_org_unit
        from app.core.exceptions import forbidden

        if not user_can_access_org_unit(db, user, dept_id):
            raise forbidden("无权查看该组织节点下的文档")
    if scope == "shared":
        rows, total = document_service.list_shared_documents(
            db, user, page=page, page_size=page_size, keyword=keyword
        )
        docs = [d for d, _ in rows]
        list_items = _list_items_with_owners(
            db, docs, include_owner_name=True, user=user
        )
        meta_by_id = {d.id: m for d, m in rows}
        list_items = [
            item.model_copy(
                update={
                    "shared_level": meta_by_id.get(item.id, {}).get("shared_level"),
                    "granted_by_name": meta_by_id.get(item.id, {}).get(
                        "granted_by_name"
                    ),
                }
            )
            for item in list_items
        ]
    elif scope == "all":
        items, total = document_service.list_all_visible_documents(
            db, user, page=page, page_size=page_size, keyword=keyword
        )
        list_items = _list_items_with_owners(
            db, items, include_owner_name=True, user=user
        )
        list_items = [
            item.model_copy(
                update={
                    "effective_level": effective_permission_level(db, user, doc),
                    "can_edit": can_edit_document(db, user, doc),
                    "can_delete": can_delete_document(db, user, doc),
                }
            )
            for item, doc in zip(list_items, items)
        ]
        list_items = _attach_folder_names(db, list_items)
    else:
        items, total = document_service.list_accessible_documents(
            db,
            user,
            page=page,
            page_size=page_size,
            keyword=keyword,
            scope=scope,
            folder_id=folder_id,
            uncategorized_only=uncategorized,
            dept_id=dept_id,
        )
        list_items = _list_items_with_owners(
            db,
            items,
            include_owner_name=scope in ("company", "department", "personal"),
            user=user,
        )
        list_items = _attach_folder_names(db, list_items)
    return ApiResponse(
        data=PageResult(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/batch-delete", response_model=ApiResponse[DocumentBatchDeleteOut])
def batch_delete_documents(
    body: DocumentBatchDeleteIn,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentBatchDeleteOut]:
    """批量删除文档（默认彻底删除，单事务提交）。"""
    result = document_service.batch_delete_documents(
        db,
        user,
        body.document_ids,
        permanent=body.permanent,
    )
    for doc_id in result.get("deleted") or []:
        audit_service.write_audit(
            db,
            user_id=user.id,
            action="document.purge" if body.permanent else "document.recycle",
            resource_type="document",
            resource_id=doc_id,
            ip_address=get_client_ip(request),
            detail={"batch": True},
        )
    return ApiResponse(data=DocumentBatchDeleteOut.model_validate(result))


@router.post("", response_model=ApiResponse[DocumentDetail])
def create_document(
    body: DocumentCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.create_document(
        db,
        user,
        title=body.title,
        description=body.description,
        scope=body.scope,
        dept_id=body.dept_id,
        folder_id=body.folder_id,
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.create",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data=_detail(db, doc, user=user))


@router.get("/my-shares", response_model=ApiResponse[PageResult[DocumentListItem]])
def list_my_shares(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[DocumentListItem]]:
    rows, total = document_service.list_my_shared_out_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    docs = [d for d, _ in rows]
    list_items = _list_items_with_owners(db, docs, include_owner_name=False, user=user)
    meta = {d.id: m for d, m in rows}
    list_items = [
        item.model_copy(
            update={
                "share_count": meta.get(item.id, {}).get("share_count"),
                "share_to_summary": meta.get(item.id, {}).get("share_to_summary"),
            }
        )
        for item in list_items
    ]
    return ApiResponse(
        data=PageResult(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/trash", response_model=ApiResponse[PageResult[DocumentListItem]])
@router.get("/recycle", response_model=ApiResponse[PageResult[DocumentListItem]], include_in_schema=False)
def list_recycle_bin(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[DocumentListItem]]:
    """个人回收站（独立路由，避免 scope 查询参数校验冲突）。"""
    items, total = document_service.list_recycle_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    list_items = _list_items_with_owners(db, items, include_owner_name=True)
    for i, item in enumerate(list_items):
        d = items[i]
        list_items[i] = item.model_copy(update={"deleted_at": d.deleted_at})
    return ApiResponse(
        data=PageResult(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/trash/empty", response_model=ApiResponse[dict])
def empty_recycle_bin(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """彻底删除当前用户回收站中的全部文档（不可恢复）。"""
    count = document_service.empty_recycle_bin(db, user)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.trash.empty",
        resource_type="document",
        resource_id=None,
        ip_address=get_client_ip(request),
        detail={"count": count},
    )
    return ApiResponse(
        data={"ok": True, "count": count, "message": f"已彻底删除 {count} 份文档"}
    )


@router.get("/{document_id}", response_model=ApiResponse[DocumentDetail])
def get_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found("Document not found")
    if doc.deleted_at:
        if not can_restore_document(db, user, doc):
            raise not_found("Document not found")
    elif not can_read_document(db, user, doc):
        raise forbidden()
    return ApiResponse(data=_detail(db, doc, user=user))


@router.patch("/{document_id}", response_model=ApiResponse[DocumentDetail])
def patch_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if body.title is None and body.description is None and body.scope is None:
        from app.core.exceptions import bad_request

        raise bad_request("请提供要更新的字段")
    doc = document_service.update_document(
        db,
        user,
        doc,
        title=body.title,
        description=body.description,
        scope=body.scope,
        dept_id=body.dept_id,
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.update",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
        detail={"title": doc.title} if body.title is not None else None,
    )
    return ApiResponse(data=_detail(db, doc, user=user))


@router.post("/{document_id}/move", response_model=ApiResponse[DocumentDetail])
def move_document(
    document_id: uuid.UUID,
    body: DocumentMoveIn,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    doc = document_service.move_document_to_folder(
        db, user, doc, folder_id=body.folder_id
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.move",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
        detail={"folder_id": str(body.folder_id) if body.folder_id else None},
    )
    return ApiResponse(data=_detail(db, doc, user=user))


@router.delete("/{document_id}/permanent", response_model=ApiResponse[dict])
def permanent_delete_document(
    document_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """彻底删除文档：清除全部版本文件、对象存储与文档记录（回收站内或列表直接删除）。"""
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    document_service.permanently_delete_document(db, user, doc)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.purge",
        resource_type="document",
        resource_id=str(document_id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data={"ok": True, "message": "已彻底删除"})


@router.post("/{document_id}/upload/prepare", response_model=ApiResponse[UploadPrepareResponse])
def prepare_upload(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file_name: str,
    mime_type: str = "application/pdf",
) -> ApiResponse[UploadPrepareResponse]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    version, upload_url = document_service.prepare_upload(
        db, user, doc, file_name=file_name, mime_type=mime_type
    )
    return ApiResponse(
        data=UploadPrepareResponse(
            document_id=doc.id,
            version_id=version.id,
            upload_url=upload_url,
            file_key=version.file_key,
        )
    )


@router.put("/{document_id}/upload/{version_id}/blob")
async def upload_document_blob(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """经平台鉴权代理上传文件到 MinIO（浏览器无法直连 minio:9000）。"""
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != doc.id:
        raise not_found("Version not found")
    data = await request.body()
    if not data:
        raise bad_request("Empty upload body")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    document_service.save_upload_blob(
        db,
        user,
        doc,
        version,
        data,
        content_type=content_type or None,
    )
    return Response(status_code=204)


@router.post(
    "/{document_id}/upload/complete",
    response_model=ApiResponse[DocumentUploadCompleteOut],
)
def complete_upload(
    document_id: uuid.UUID,
    body: UploadCompleteRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentUploadCompleteOut]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    version = db.get(DocumentVersion, body.version_id)
    if not version or version.document_id != doc.id:
        raise not_found("Version not found")
    doc = document_service.complete_upload(
        db,
        user,
        doc,
        version,
        file_size=body.file_size,
        checksum=body.checksum,
        change_description=body.change_description,
    )
    job_id = None
    if knowledge.enabled():
        job_id = knowledge.schedule_sync_after_ingest(
            background_tasks,
            doc.id,
            user.id,
            version_id=version.id,
        )
    return ApiResponse(
        data=DocumentUploadCompleteOut(
            document=_detail(db, doc, user=user),
            knowledge_job_id=job_id,
        )
    )


def _attachment_disposition(file_name: str) -> str:
    name = (file_name or "download").replace("\n", "").replace("\r", "")
    ascii_name = "".join(
        c if ord(c) < 128 and c not in ('"', "\\") else "_" for c in name
    ).strip() or "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(name)}"
    )


@router.get("/{document_id}/download", response_model=ApiResponse[dict])
def download_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    url = document_service.get_download_url(db, user, doc)
    if not url:
        raise forbidden("No download permission or no file uploaded")
    return ApiResponse(data={"download_url": url, "expires_in": 3600})


@router.get("/{document_id}/file")
def download_document_file(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    version_id: uuid.UUID | None = None,
) -> Response:
    """经平台鉴权代理下载文件；不传 version_id 时下载当前版本。"""
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    content, file_name, mime_type = document_service.read_document_file_bytes(
        db, user, doc, version_id=version_id
    )
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": _attachment_disposition(file_name)},
    )


@router.post(
    "/{document_id}/sync-knowflow",
    response_model=ApiResponse[DocumentKnowflowSyncOut],
)
def sync_document_knowflow(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentKnowflowSyncOut]:
    """将当前文档强制同步到分级 KnowFlow 知识库（个人/部门/公司）。"""
    import logging

    from app.core.user_messages import (
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        KNOWLEDGE_SYNC_DISABLED,
        KNOWLEDGE_SYNC_FAILED,
    )
    from app.services.document_service import resolve_current_version

    logger = logging.getLogger(__name__)

    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_read_document(db, user, doc):
        raise forbidden()
    if not resolve_current_version(db, doc):
        raise forbidden("文档尚未上传文件，无法同步知识库")

    if not knowledge.enabled():
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                message=KNOWLEDGE_SYNC_DISABLED,
            )
        )

    if not knowledge.stack_reachable():
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                message=KNOWLEDGE_SERVICE_UNAVAILABLE,
            )
        )

    from app.services.knowledge_sync_job_service import enqueue_document_knowledge_index

    job = enqueue_document_knowledge_index(
        db,
        user_id=user.id,
        document_id=doc.id,
        version_id=doc.current_version_id,
        force=True,
        document_title=doc.title,
    )
    if job:
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                queued=True,
                knowledge_job_id=job.id,
                message="已加入后台任务，正在同步并解析知识库，请在「后台任务」查看进度。",
            )
        )
    return ApiResponse(
        data=DocumentKnowflowSyncOut(
            knowflow_synced=False,
            message=KNOWLEDGE_SYNC_FAILED,
        )
    )


@router.get(
    "/{document_id}/access-control",
    response_model=ApiResponse[DocumentAccessControlOut],
)
def document_access_control(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentAccessControlOut]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    if doc.deleted_at:
        if not can_restore_document(db, user, doc):
            raise not_found()
    elif not can_read_document(db, user, doc):
        raise forbidden()
    return ApiResponse(
        data=DocumentAccessControlOut(
            can_grant=can_grant_document_permissions(db, user, doc),
            can_deny=can_manage_document_denials(db, user, doc),
            is_owner=doc.owner_id == user.id,
            can_view=can_read_document(db, user, doc),
            can_query=can_query_document(db, user, doc),
            can_edit=can_edit_document(db, user, doc),
            can_delete=can_delete_document(db, user, doc),
            can_manage=can_manage_document(db, user, doc),
            can_restore=can_restore_document(db, user, doc),
            effective_level=effective_permission_level(db, user, doc),
        )
    )


@router.patch("/{document_id}/status", response_model=ApiResponse[DocumentDetail])
def patch_document_status(
    document_id: uuid.UUID,
    body: DocumentStatusUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_manage_document(db, user, doc):
        raise forbidden("无权修改文档状态")
    doc = document_service.update_document_status(db, doc, body.status)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.status",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
        detail={"status": body.status},
    )
    return ApiResponse(data=_detail(db, doc, user=user))


@router.post("/{document_id}/restore", response_model=ApiResponse[DocumentDetail])
def restore_document(
    document_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or not doc.deleted_at:
        raise not_found()
    if not can_restore_document(db, user, doc):
        raise forbidden("无权恢复该文档")
    doc = document_service.restore_document(db, doc)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.restore",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data=_detail(db, doc, user=user))


@router.get(
    "/{document_id}/acl-candidates",
    response_model=ApiResponse[AclPickerOut],
)
def list_acl_candidates(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AclPickerOut]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not (
        can_grant_document_permissions(db, user, doc)
        or can_manage_document_denials(db, user, doc)
    ):
        raise forbidden()
    data = document_service.list_acl_picker_data(db, doc)
    return ApiResponse(data=AclPickerOut.model_validate(data))


@router.get("/{document_id}/permissions", response_model=ApiResponse[list[DocumentShareOut]])
def list_permissions(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[DocumentShareOut]]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_grant_document_permissions(db, user, doc):
        raise forbidden()
    shares = document_service.list_document_shares(db, document_id)
    return ApiResponse(
        data=[DocumentShareOut.model_validate(s) for s in shares]
    )


@router.post(
    "/{document_id}/permissions/batch",
    response_model=ApiResponse[list[DocumentShareOut]],
)
def batch_share_permissions(
    document_id: uuid.UUID,
    body: DocumentShareBatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[DocumentShareOut]]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    shares = document_service.set_document_shares(
        db,
        user,
        doc,
        user_ids=body.user_ids,
        level=body.level,
    )
    _sync_kb_grants_if_enabled(db, doc)
    return ApiResponse(data=[DocumentShareOut.model_validate(s) for s in shares])


@router.delete(
    "/{document_id}/permissions/users/{target_user_id}",
    response_model=ApiResponse[None],
)
def revoke_user_share(
    document_id: uuid.UUID,
    target_user_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    document_service.revoke_document_share(db, user, doc, target_user_id)
    _sync_kb_grants_if_enabled(db, doc)
    return ApiResponse()


@router.post("/{document_id}/permissions", response_model=ApiResponse[DocumentShareOut])
def grant_permission(
    document_id: uuid.UUID,
    body: DocumentGrant,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentShareOut]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    document_service.grant_permission(
        db,
        user,
        doc,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        level=body.level,
        expires_at=body.expires_at,
    )
    _sync_kb_grants_if_enabled(db, doc)
    shares = document_service.list_document_shares(db, document_id)
    match = next((s for s in shares if s["user_id"] == body.subject_id), None)
    if not match:
        raise not_found()
    return ApiResponse(data=DocumentShareOut.model_validate(match))


@router.delete("/{document_id}/permissions/{perm_id}", response_model=ApiResponse[None])
def revoke_permission(
    document_id: uuid.UUID,
    perm_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    document_service.revoke_permission(db, user, doc, perm_id)
    _sync_kb_grants_if_enabled(db, doc)
    return ApiResponse()


@router.get("/{document_id}/denials", response_model=ApiResponse[list[DocumentDenialOut]])
def list_denials(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[DocumentDenialOut]]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_manage_document_denials(db, user, doc):
        raise forbidden()
    rows = document_workflow_service.list_denials(db, document_id)
    out: list[DocumentDenialOut] = []
    for r in rows:
        item = DocumentDenialOut.model_validate(r)
        out.append(
            item.model_copy(update={"user_name": _owner_display(db, r.user_id)})
        )
    return ApiResponse(data=out)


@router.post("/{document_id}/denials", response_model=ApiResponse[DocumentDenialOut])
def deny_access(
    document_id: uuid.UUID,
    body: DocumentDenialCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDenialOut]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    row = document_workflow_service.deny_user_access(
        db, user, doc, user_id=body.user_id, reason=body.reason
    )
    _sync_kb_grants_if_enabled(db, doc)
    return ApiResponse(data=DocumentDenialOut.model_validate(row))


@router.delete("/{document_id}/denials/{target_user_id}", response_model=ApiResponse[None])
def lift_denial(
    document_id: uuid.UUID,
    target_user_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    document_workflow_service.lift_denial(db, user, doc, user_id=target_user_id)
    return ApiResponse()


@router.delete(
    "/{document_id}/versions/{version_id}",
    response_model=ApiResponse[DeleteDocumentVersionResult],
)
def delete_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DeleteDocumentVersionResult]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != doc.id:
        raise not_found("版本不存在")
    result = document_service.delete_document_version(
        db, user, doc, version, deleted_by=user.id
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action=(
            "document.recycle"
            if result.get("document_deleted")
            else "document.version.delete"
        ),
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data=DeleteDocumentVersionResult.model_validate(result))


@router.delete("/{document_id}", response_model=ApiResponse[dict])
def delete_document(
    document_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_delete_document(db, user, doc):
        raise forbidden("无权删除该文档")
    document_service.soft_delete_document(db, doc, deleted_by=user.id)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.recycle",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data={"ok": True, "message": "已移入回收站"})
