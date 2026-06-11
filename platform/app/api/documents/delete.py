from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.core.document_scope import can_delete_document
from app.core.exceptions import forbidden, not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.services import audit_service, document_service

router = APIRouter()

@router.delete("/{document_id}", response_model=ApiResponse[dict])
def delete_document(
    document_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found()
    if not can_delete_document(db, user, doc):
        raise forbidden("无权删除该文档")
    document_service.permanently_delete_document(
        db, user, doc, defer_knowflow=True
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.purge",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data={"ok": True, "message": "已删除"})
