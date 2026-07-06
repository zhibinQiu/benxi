from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.api.documents.serializers import (
    document_detail as _detail,
)
from app.api.documents.serializers import (
    owner_display as _owner_display,
)
from app.api.documents.serializers import (
    sync_kb_grants_if_enabled as _sync_kb_grants_if_enabled,
)
from app.core.document_scope import (
    can_grant_document_permissions,
    can_manage_document,
    can_manage_document_denials,
    can_modify_document,
    can_query_document,
    can_read_document,
    can_restore_document,
    effective_permission_level,
)
from app.core.exceptions import forbidden, not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import (
    AclPickerOut,
    DocumentAccessControlOut,
    DocumentDetail,
    DocumentGrant,
    DocumentShareBatchIn,
    DocumentShareOut,
    DocumentStatusUpdate,
)
from app.schemas.document_workflow import DocumentDenialCreate, DocumentDenialOut
from app.services import audit_service, document_service, document_workflow_service

router = APIRouter()

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
            can_modify=can_modify_document(db, user, doc),
            can_edit=can_modify_document(db, user, doc),
            can_delete=can_modify_document(db, user, doc),
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
    doc = document_service.restore_document(db, doc, user_id=user.id)
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
