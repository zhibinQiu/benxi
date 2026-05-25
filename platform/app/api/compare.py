"""文档对比 — 左右双栏、差异与高亮检索。"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.compare_service import run_compare_job

logger = logging.getLogger(__name__)

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request, forbidden, not_found
from app.database import get_db
from app.models.compare import CompareJob
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.compare import (
    CompareDirectSearchRequest,
    CompareDocumentOut,
    CompareJobCreate,
    CompareJobOut,
    CompareSearchHitOut,
    CompareSearchRequest,
)
from app.services import document_service
from app.services import compare_service
from app.services.compare_service import (
    create_compare_job,
    get_user_compare_job,
    job_to_dict,
    list_compare_documents,
    search_compare_documents,
    search_compare_job,
)


def _run_compare_in_background(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        run_compare_job(db, job_id)
    except Exception:
        logger.exception("文档对比任务失败 job_id=%s", job_id)
        job = db.get(CompareJob, job_id)
        if job:
            from app.models.compare import CompareStatus

            job.status = CompareStatus.failed.value
            job.error_message = "对比处理失败，请稍后重试"
            db.commit()
    finally:
        db.close()

router = APIRouter(
    prefix="/compare",
    tags=["compare"],
    dependencies=[Depends(require_feature("doc_compare"))],
)


def _require_job(db: Session, job_id: str, user: User):
    try:
        uid = uuid.UUID(job_id)
    except ValueError as e:
        raise not_found("任务不存在") from e
    job = get_user_compare_job(db, uid, user.id)
    if not job:
        raise forbidden("无权访问该任务")
    return job


@router.get("/documents", response_model=ApiResponse[PageResult[CompareDocumentOut]])
def list_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[CompareDocumentOut]]:
    rows, total = list_compare_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        CompareDocumentOut(
            id=r["id"],
            title=r["title"],
            file_name=r["file_name"],
            file_size=r["file_size"],
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]
    return ApiResponse(
        data=PageResult(items=items, total=total, page=page, page_size=page_size)
    )


@router.post("/jobs", response_model=ApiResponse[CompareJobOut])
def start_compare(
    body: CompareJobCreate,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[CompareJobOut]:
    try:
        left = uuid.UUID(body.left_document_id)
        right = uuid.UUID(body.right_document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    job = create_compare_job(
        db,
        user,
        left_document_id=left,
        right_document_id=right,
        sync_knowflow=body.sync_knowflow,
    )
    background_tasks.add_task(_run_compare_in_background, job.id)
    data = job_to_dict(db, job)
    return ApiResponse(data=CompareJobOut(**data))


@router.get("/jobs/{job_id}", response_model=ApiResponse[CompareJobOut])
def get_job(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[CompareJobOut]:
    job = _require_job(db, job_id, user)
    return ApiResponse(data=CompareJobOut(**job_to_dict(db, job)))


@router.post("/search", response_model=ApiResponse[list[CompareSearchHitOut]])
def search_documents(
    body: CompareDirectSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[CompareSearchHitOut]]:
    try:
        right_id = uuid.UUID(body.right_document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    hits = search_compare_documents(
        db,
        user,
        right_document_id=right_id,
        query=body.query.strip(),
        sync_knowflow=body.sync_knowflow,
        field_match=body.field_match,
    )
    return ApiResponse(data=[CompareSearchHitOut(**h) for h in hits])


@router.post("/jobs/{job_id}/search", response_model=ApiResponse[list[CompareSearchHitOut]])
def search_job(
    job_id: str,
    body: CompareSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[CompareSearchHitOut]]:
    job = _require_job(db, job_id, user)
    scope = body.scope if body.scope in ("right", "both") else "right"
    hits = search_compare_job(
        db,
        job,
        body.query.strip(),
        scope=scope,
        field_match=body.field_match,
    )
    return ApiResponse(
        data=[CompareSearchHitOut(**h) for h in hits],
    )


@router.get("/documents/{document_id}/file")
def document_file(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        did = uuid.UUID(document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    data, mime, file_name = compare_service.get_document_file_bytes(db, user, did)
    safe_name = quote(file_name)
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{safe_name}"},
    )


@router.get("/documents/{document_id}/content", response_model=ApiResponse[dict])
def document_content(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    try:
        did = uuid.UUID(document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    return ApiResponse(data=compare_service.get_document_content(db, user, did))


@router.get("/documents/{document_id}/download", response_model=ApiResponse[dict])
def document_download(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    try:
        did = uuid.UUID(document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    doc = document_service.get_document(db, did)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    url = document_service.get_download_url(db, user, doc)
    if not url:
        raise forbidden("无权预览或文件未上传")
    return ApiResponse(data={"download_url": url, "expires_in": 3600})
