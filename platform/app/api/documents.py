from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user
from app.core.exceptions import forbidden, not_found
from app.core.permissions import PermissionLevel, can_access_document
from app.database import get_db
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.document import (
    DocumentCreate,
    DocumentDetail,
    DocumentGrant,
    DocumentListItem,
    DocumentPermissionOut,
    DocumentVersionOut,
    UploadCompleteRequest,
    UploadPrepareResponse,
)
from app.services import audit_service, document_service, job_service

router = APIRouter(prefix="/documents", tags=["documents"])


def _detail(db: Session, doc: Document) -> DocumentDetail:
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_no.desc())
        ).all()
    )
    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        status=doc.status,
        owner_id=doc.owner_id,
        dept_id=doc.dept_id,
        current_version_id=doc.current_version_id,
        description=doc.description,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        versions=[DocumentVersionOut.model_validate(v) for v in versions],
    )


@router.get("", response_model=ApiResponse[PageResult[DocumentListItem]])
def list_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[DocumentListItem]]:
    items, total = document_service.list_accessible_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    return ApiResponse(
        data=PageResult(
            items=[DocumentListItem.model_validate(d) for d in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


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
        dept_id=body.dept_id,
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.create",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
    )
    return ApiResponse(data=_detail(db, doc))


@router.get("/{document_id}", response_model=ApiResponse[DocumentDetail])
def get_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("Document not found")
    if not can_access_document(db, user, doc, PermissionLevel.read.value):
        raise forbidden()
    return ApiResponse(data=_detail(db, doc))


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


@router.post("/{document_id}/upload/complete", response_model=ApiResponse[DocumentDetail])
def complete_upload(
    document_id: uuid.UUID,
    body: UploadCompleteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentDetail]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    version = db.get(DocumentVersion, body.version_id)
    if not version or version.document_id != doc.id:
        raise not_found("Version not found")
    doc = document_service.complete_upload(
        db, user, doc, version, file_size=body.file_size, checksum=body.checksum
    )
    return ApiResponse(data=_detail(db, doc))


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


@router.get("/{document_id}/permissions", response_model=ApiResponse[list[DocumentPermissionOut]])
def list_permissions(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[DocumentPermissionOut]]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if doc.owner_id != user.id:
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "doc.grant"):
            raise forbidden()
    perms = document_service.list_document_permissions(db, document_id)
    return ApiResponse(
        data=[DocumentPermissionOut.model_validate(p) for p in perms]
    )


@router.post("/{document_id}/permissions", response_model=ApiResponse[DocumentPermissionOut])
def grant_permission(
    document_id: uuid.UUID,
    body: DocumentGrant,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentPermissionOut]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    perm = document_service.grant_permission(
        db,
        user,
        doc,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        level=body.level,
        expires_at=body.expires_at,
    )
    return ApiResponse(data=DocumentPermissionOut.model_validate(perm))


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
    if doc.owner_id != user.id:
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "doc.grant"):
            raise forbidden()
    document_service.revoke_permission(db, perm_id)
    return ApiResponse()


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
    if not can_access_document(db, user, doc, PermissionLevel.delete.value):
        raise forbidden()
    document_service.soft_delete_document(db, doc)
    job = job_service.enqueue_delete_document(db, doc.id, user.id)
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="document.delete",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=get_client_ip(request),
        detail={"job_id": str(job.id)},
    )
    return ApiResponse(data={"job_id": str(job.id), "status": job.status})
