from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.core.exceptions import not_found
from app.database import get_db
from app.models.document import DocumentVersion
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import DeleteDocumentVersionResult
from app.services import audit_service, document_service

router = APIRouter()

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
            "document.purge"
            if result.get("document_deleted")
            else "document.version.delete"
        ),
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data=DeleteDocumentVersionResult.model_validate(result))
