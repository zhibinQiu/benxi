from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.exceptions import forbidden, not_found
from app.core.async_db import detach_request_db
from app.database import get_db
from app.models.job import Job
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.job import JobBatchDeleteIn, JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=ApiResponse[PageResult[JobOut]])
def list_jobs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    job_type: str | None = Query(None),
) -> ApiResponse[PageResult[JobOut]]:
    from app.services import job_service

    items, total = job_service.list_jobs(
        db, user.id, page=page, page_size=page_size, job_type=job_type
    )
    return ApiResponse(
        data=PageResult(
            items=[JobOut.model_validate(j) for j in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.delete("/clear", response_model=ApiResponse[dict])
def clear_jobs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    scope: str = Query("finished", pattern="^(finished|all)$"),
) -> ApiResponse[dict]:
    from app.services import job_service

    deleted = job_service.clear_jobs(db, user.id, scope=scope)
    return ApiResponse(data={"deleted": deleted, "scope": scope})


@router.post("/batch-delete", response_model=ApiResponse[dict])
def batch_delete_jobs(
    body: JobBatchDeleteIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    from app.services import job_service

    deleted = job_service.delete_jobs_by_ids(db, user.id, body.job_ids)
    return ApiResponse(data={"deleted": deleted, "requested": len(body.job_ids)})


@router.post("/{job_id}/cancel", response_model=ApiResponse[JobOut])
def cancel_job(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[JobOut]:
    from app.services import job_service

    job = db.get(Job, job_id)
    if not job:
        raise not_found("任务不存在")
    if job.created_by != user.id:
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "admin.user"):
            raise forbidden()
    job = job_service.cancel_job(db, job)
    return ApiResponse(data=JobOut.model_validate(job))


@router.get("/{job_id}", response_model=ApiResponse[JobOut])
def get_job(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[JobOut]:
    job = db.get(Job, job_id)
    if not job:
        raise not_found("Job not found")
    if job.created_by != user.id:
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "admin.user"):
            raise forbidden()
    return ApiResponse(data=JobOut.model_validate(job))


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = db.get(Job, job_id)
    if not job:
        raise not_found("Job not found")
    if job.created_by != user.id:
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "admin.user"):
            raise forbidden()

    detach_request_db(db)

    from app.database import SessionLocal
    from app.api.streaming_utils import poll_and_stream

    def _fetch_payload(poll_db: Session) -> dict | None:
        polled = poll_db.get(Job, job_id)
        if not polled:
            return None
        return JobOut.model_validate(polled).model_dump(mode="json")

    return EventSourceResponse(
        poll_and_stream(
            SessionLocal,
            _fetch_payload,
            terminal_statuses=frozenset({"done", "failed", "cancelled"}),
        )
    )
