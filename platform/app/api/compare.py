"""文档对比 — 左右双栏、差异与高亮检索。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request, forbidden, not_found
from app.database import SessionLocal, get_db
from app.models.compare import CompareJob
from app.models.document_version_compare import VersionCompareStatus
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
from app.schemas.version_compare import (
    VersionCompareAskIn,
    VersionCompareBatchIn,
    VersionCompareRelationOut,
)
from app.services import compare_service, document_service
from app.services.compare_service import (
    create_compare_job,
    get_user_compare_job,
    job_to_dict,
    list_compare_documents,
    run_compare_job,
    search_compare_documents,
    search_compare_job,
)
from app.services.version_compare_service import (
    get_relation_by_pair,
    list_document_version_relations,
    load_adjacent_version_relations,
    load_version_pair_relation,
)
from app.services.version_compare_summary_service import answer_version_compare_question

logger = logging.getLogger(__name__)


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


@router.get("/jobs/{job_id}/events")
async def compare_job_events(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = _require_job(db, job_id, user)

    async def generator():
        last_status = None
        for _ in range(600):
            poll_db = SessionLocal()
            try:
                polled = get_user_compare_job(poll_db, job.id, user.id)
                if not polled:
                    break
                payload = job_to_dict(poll_db, polled)
            finally:
                poll_db.close()
            if payload.get("status") != last_status:
                last_status = payload.get("status")
                yield {"event": "status", "data": json.dumps(payload, default=str)}
            if payload.get("status") in ("done", "failed"):
                yield {"event": "complete", "data": json.dumps(payload, default=str)}
                break
            await asyncio.sleep(1)
        else:
            yield {
                "event": "timeout",
                "data": json.dumps({"message": "poll timeout"}, default=str),
            }

    return EventSourceResponse(generator())


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


@router.get(
    "/documents/{document_id}/version-compare",
    response_model=ApiResponse[VersionCompareRelationOut],
)
def get_version_compare(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    left_version_id: str = Query(..., description="参照版本（较早）"),
    right_version_id: str = Query(..., description="对比版本（较新）"),
) -> ApiResponse[VersionCompareRelationOut]:
    """只读：返回已预计算入库的版本对 diff（不在此触发新计算）。"""
    try:
        did = uuid.UUID(document_id)
        left_vid = uuid.UUID(left_version_id)
        right_vid = uuid.UUID(right_version_id)
    except ValueError as e:
        raise bad_request("无效的 ID") from e
    from app.services.version_compare_service import load_version_pair_relation

    data = load_version_pair_relation(db, user, did, left_vid, right_vid)
    return ApiResponse(data=VersionCompareRelationOut(**data))


@router.get(
    "/documents/{document_id}/version-compare/adjacent",
    response_model=ApiResponse[list[VersionCompareRelationOut]],
)
def get_adjacent_version_compare(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    version_ids: str = Query(..., description="逗号分隔的版本 ID，按时间线取相邻对"),
) -> ApiResponse[list[VersionCompareRelationOut]]:
    """只读：加载时间线相邻版本对的预计算 diff。"""
    try:
        did = uuid.UUID(document_id)
        vids = [uuid.UUID(x.strip()) for x in version_ids.split(",") if x.strip()]
    except ValueError as e:
        raise bad_request("无效的 ID") from e

    rows = load_adjacent_version_relations(db, user, did, vids)
    return ApiResponse(data=[VersionCompareRelationOut(**r) for r in rows])


@router.get(
    "/documents/{document_id}/version-compare/relations",
    response_model=ApiResponse[list[VersionCompareRelationOut]],
)
def list_version_compare_relations(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[VersionCompareRelationOut]]:
    try:
        did = uuid.UUID(document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    rows = list_document_version_relations(db, user, did)
    return ApiResponse(data=[VersionCompareRelationOut(**r) for r in rows])


@router.post(
    "/documents/{document_id}/version-compare/batch",
    response_model=ApiResponse[list[VersionCompareRelationOut]],
)
def batch_version_compare(
    document_id: str,
    body: VersionCompareBatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[VersionCompareRelationOut]]:
    """按勾选版本列表只读加载相邻版本对 diff（上传时已后台预计算）。"""
    try:
        did = uuid.UUID(document_id)
        vids = [uuid.UUID(x) for x in body.version_ids]
    except ValueError as e:
        raise bad_request("无效的 ID") from e

    rows = load_adjacent_version_relations(db, user, did, vids)
    return ApiResponse(data=[VersionCompareRelationOut(**r) for r in rows])


@router.post(
    "/documents/{document_id}/version-compare/ask",
    response_model=ApiResponse[dict],
)
def version_compare_ask(
    document_id: str,
    body: VersionCompareAskIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """基于入库 diff + LLM 总结回答版本差异问题。"""
    try:
        did = uuid.UUID(document_id)
        left_vid = uuid.UUID(body.left_version_id)
        right_vid = uuid.UUID(body.right_version_id)
    except ValueError as e:
        raise bad_request("无效的 ID") from e
    data = load_version_pair_relation(db, user, did, left_vid, right_vid)
    if data.get("status") != VersionCompareStatus.done.value:
        raise bad_request("该版本差异尚未预计算完成，请稍后再试")
    rel = get_relation_by_pair(db, did, left_vid, right_vid)
    if not rel:
        from app.core.exceptions import not_found

        raise not_found("版本对比不存在")
    answer = answer_version_compare_question(db, rel, body.question)
    return ApiResponse(
        data={
            "answer": answer,
            "relation": VersionCompareRelationOut(**data),
        }
    )


@router.get("/documents/{document_id}/content", response_model=ApiResponse[dict])
def document_content(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    version_id: str | None = Query(None, description="指定历史版本"),
) -> ApiResponse[dict]:
    try:
        did = uuid.UUID(document_id)
    except ValueError as e:
        raise bad_request("无效的文档 ID") from e
    if version_id:
        try:
            vid = uuid.UUID(version_id)
        except ValueError as e:
            raise bad_request("无效的版本 ID") from e
        return ApiResponse(
            data=compare_service.get_document_content_for_version(
                db, user, did, vid
            )
        )
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
