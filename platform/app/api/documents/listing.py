from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.api.documents.serializers import (
    attach_folder_names as _attach_folder_names,
)
from app.api.documents.serializers import (
    document_detail as _detail,
)
from app.api.documents.serializers import (
    list_items_with_owners as _list_items_with_owners,
)
from app.config import get_settings
from app.core.document_scope import (
    library_companies_for_user,
    library_departments_for_user,
    library_folders,
    library_teams_for_user,
    personal_library_owners_for_user,
)
from app.core.document_upload_limits import document_upload_max_label
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.document import (
    DocumentBatchDeleteIn,
    DocumentBatchDeleteOut,
    DocumentCreate,
    DocumentDetail,
    DocumentFolderOut,
    DocumentLibraryOut,
    DocumentListItem,
)
from app.services import audit_service, document_service
from app.core.platform_cache import invalidate_document_caches

router = APIRouter()

@router.get("/library", response_model=ApiResponse[DocumentLibraryOut])
def document_library(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentLibraryOut]:
    from app.core.platform_cache import cache_get_or_set, document_library_cache_key

    settings = get_settings()
    cache_key = document_library_cache_key(str(user.id))
    ttl = max(5, int(settings.document_library_cache_ttl_sec))

    def build_payload() -> dict:
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
        personal_owner_rows = [
            {"id": str(d["id"]), "name": d["name"]}
            for d in personal_library_owners_for_user(db, user)
        ]
        return {
            "folders": folders,
            "companies": company_rows,
            "departments": dept_rows,
            "teams": team_rows,
            "personal_owners": personal_owner_rows,
            "upload_max_file_mb": settings.document_upload_max_file_mb,
            "upload_max_size_label": document_upload_max_label(),
        }

    data = cache_get_or_set(cache_key, build_payload, ttl=ttl)
    return ApiResponse(
        data=DocumentLibraryOut(
            folders=[DocumentFolderOut.model_validate(f) for f in data["folders"]],
            companies=data["companies"],
            departments=data["departments"],
            teams=data["teams"],
            personal_owners=data.get("personal_owners") or [],
            upload_max_file_mb=data["upload_max_file_mb"],
            upload_max_size_label=data["upload_max_size_label"],
        )
    )


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
    owner_id: uuid.UUID | None = None,
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
            owner_id=owner_id,
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
            action="document.purge",
            resource_type="document",
            resource_id=doc_id,
            ip_address=get_client_ip(request),
            detail={"batch": True},
        )
    invalidate_document_caches(str(user.id))
    return ApiResponse(data=DocumentBatchDeleteOut.model_validate(result))


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
    invalidate_document_caches(str(user.id))
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
