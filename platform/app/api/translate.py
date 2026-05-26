"""PDF translation — platform jobs + pdf2zh proxy."""

from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.core.exceptions import bad_request, forbidden, not_found
from app.services import document_service
from app.schemas.translate import TranslatableDocumentOut
from app.database import get_db
from app.integrations.pdf2zh_client import pdf2zh_base_url
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.services.audit_service import write_audit
from app.services.translate_service import (
    create_translate_job,
    get_user_job,
    job_to_dict,
    list_translate_jobs,
    pdf2zh_job_id,
    sync_job_from_pdf2zh,
)

router = APIRouter(
    prefix="/translate",
    tags=["translate"],
    dependencies=[Depends(require_feature("pdf_translate"))],
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=pdf2zh_base_url(), timeout=httpx.Timeout(600.0))


def _require_job(db: Session, job_id: str, user: User):
    try:
        uid = uuid.UUID(job_id)
    except ValueError as e:
        raise not_found("任务不存在") from e
    job = get_user_job(db, uid, user.id)
    if not job:
        raise forbidden("无权访问该任务")
    return job


@router.get("/meta")
async def translate_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    async with _client() as client:
        try:
            r = await client.get("/api/meta")
            r.raise_for_status()
            return ApiResponse(data=r.json())
        except httpx.HTTPError as e:
            raise HTTPException(503, f"无法连接翻译服务: {e}") from e


@router.get("/documents", response_model=ApiResponse[PageResult[TranslatableDocumentOut]])
def list_translatable_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[TranslatableDocumentOut]]:
    """可翻译的文档库 PDF（未删除、已启用，且当前用户具备「可查询」及以上权限）。"""
    rows, total = document_service.list_translatable_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        TranslatableDocumentOut(
            id=doc.id,
            title=doc.title,
            file_name=ver.file_name,
            file_size=ver.file_size,
            updated_at=doc.updated_at,
        )
        for doc, ver in rows
    ]
    return ApiResponse(
        data=PageResult(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/jobs")
async def list_jobs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PageResult[dict]]:
    items, total = list_translate_jobs(db, user.id, page=page, page_size=page_size)
    return ApiResponse(
        data=PageResult(
            items=[job_to_dict(j) for j in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/jobs")
async def create_job(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    lang_in: str = Form("en"),
    lang_out: str = Form("zh-CN"),
    service: str = Form(...),
    file: UploadFile | None = File(None),
    document_id: str | None = Form(None),
    glossary_files: list[UploadFile] | None = File(None),
) -> ApiResponse[dict]:
    source_doc_id: uuid.UUID | None = None
    if file and document_id:
        raise bad_request("请勿同时上传文件和选择文档库文档")
    if not file and not document_id:
        raise bad_request("请上传 PDF 或从文档库选择文档")

    if document_id:
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError as e:
            raise bad_request("无效的文档 ID") from e
        file_bytes, file_name, _doc = document_service.read_document_pdf_bytes(
            db, user, doc_uuid
        )
        source_doc_id = doc_uuid
        content_type = "application/pdf"
    else:
        file_bytes = await file.read()
        file_name = file.filename or "document.pdf"
        content_type = file.content_type or "application/pdf"

    multipart_files = [
        ("file", (file_name, file_bytes, content_type)),
    ]
    if glossary_files:
        for g in glossary_files:
            multipart_files.append(
                (
                    "glossary_files",
                    (
                        g.filename or "glossary.csv",
                        await g.read(),
                        g.content_type or "text/csv",
                    ),
                )
            )
    data = {"lang_in": lang_in, "lang_out": lang_out, "service": service}

    async with _client() as client:
        try:
            r = await client.post("/api/jobs", files=multipart_files, data=data)
            r.raise_for_status()
            remote = r.json()
        except httpx.HTTPError as e:
            detail = ""
            if hasattr(e, "response") and e.response is not None:
                detail = e.response.text
            raise HTTPException(502, f"翻译任务创建失败: {detail or e}") from e

    job = create_translate_job(
        db,
        user_id=user.id,
        pdf2zh_job_id_str=remote["job_id"],
        file_name=file_name,
        lang_in=lang_in,
        lang_out=lang_out,
        service=service,
        document_id=source_doc_id,
    )

    audit_detail: dict = {"pdf2zh_job_id": remote["job_id"], "file_name": file_name}
    if source_doc_id:
        audit_detail["document_id"] = str(source_doc_id)
    write_audit(
        db,
        user_id=user.id,
        action="translate.job_create",
        resource_type="translate_job",
        resource_id=str(job.id),
        ip_address=get_client_ip(request),
        detail=audit_detail,
    )

    result = job_to_dict(job)
    result["message"] = "翻译已在后台执行，可离开页面，稍后在「后台任务」或「消息」中查看结果"
    return ApiResponse(data=result)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    job = _require_job(db, job_id, user)
    if job.status not in ("done", "failed", "cancelled"):
        job = sync_job_from_pdf2zh(db, job)
    return ApiResponse(data=job_to_dict(job))


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = _require_job(db, job_id, user)
    zid = pdf2zh_job_id(job)
    if not zid:
        raise not_found("pdf2zh 任务 ID 缺失")

    async def stream():
        async with _client() as client:
            try:
                async with client.stream("GET", f"/api/jobs/{zid}/events") as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        yield chunk
            except httpx.HTTPError:
                yield b'event: error\ndata: {"error":"sse proxy failed"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}/download/{kind}")
async def download_file(
    job_id: str,
    kind: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = _require_job(db, job_id, user)
    zid = pdf2zh_job_id(job)
    if not zid:
        raise not_found("pdf2zh 任务 ID 缺失")
    async with _client() as client:
        r = await client.get(f"/api/jobs/{zid}/download/{kind}")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        headers = {}
        if disp := r.headers.get("content-disposition"):
            headers["Content-Disposition"] = disp
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )
