from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.documents.serializers import (
    attachment_disposition as _attachment_disposition,
)
from app.api.documents.serializers import (
    document_detail as _detail,
)
from app.core.exceptions import bad_request, forbidden, not_found
from app.database import get_db
from app.domains.knowledge import knowledge
from app.models.document import DocumentVersion
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import (
    DocumentUploadCompleteOut,
    UploadCompleteRequest,
    UploadPrepareResponse,
)
from app.services import document_service

router = APIRouter()

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
    from app.services.documents.post_upload import schedule_post_upload_processing

    schedule_post_upload_processing(doc.id, version.id, user.id)
    return ApiResponse(
        data=DocumentUploadCompleteOut(
            document=_detail(db, doc, user=user),
            knowledge_job_id=str(job_id) if job_id else None,
        )
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
