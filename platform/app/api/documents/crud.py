from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.api.documents.serializers import document_detail as _detail
from app.core.document_scope import (
    can_read_document,
    can_restore_document,
)
from app.core.exceptions import forbidden, not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import (
    DocumentDetail,
    DocumentMoveIn,
    DocumentUpdate,
)
from app.services import audit_service, document_service

router = APIRouter()

@router.get("/{document_id}", response_model=ApiResponse[DocumentDetail])
def get_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    live_index: bool = Query(
        False,
        description="为 true 时实时拉取 RAGFlow 索引进度（较慢，适合手动刷新）",
    ),
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found("Document not found")
    if doc.deleted_at:
        if not can_restore_document(db, user, doc):
            raise not_found("Document not found")
    elif not can_read_document(db, user, doc):
        raise forbidden()
    return ApiResponse(data=_detail(db, doc, user=user, live_index=live_index))


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
    document_service.permanently_delete_document(
        db, user, doc, defer_knowflow=True
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.purge",
        resource_type="document",
        resource_id=str(document_id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data={"ok": True, "message": "已彻底删除"})
