from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.exceptions import forbidden, not_found
from app.database import get_db
from app.models.job import Job
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.job import JobOut

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

    async def generator():
        from app.database import SessionLocal

        last_status = None
        for _ in range(600):
            poll_db = SessionLocal()
            try:
                polled = poll_db.get(Job, job_id)
                if not polled:
                    break
                payload = JobOut.model_validate(polled).model_dump(mode="json")
            finally:
                poll_db.close()
            if payload["status"] != last_status:
                last_status = payload["status"]
                yield {"event": "status", "data": json.dumps(payload, default=str)}
            if payload["status"] in ("done", "failed", "cancelled"):
                yield {"event": "complete", "data": json.dumps(payload, default=str)}
                break
            await asyncio.sleep(1)
        else:
            yield {
                "event": "timeout",
                "data": json.dumps({"message": "poll timeout"}, default=str),
            }

    return EventSourceResponse(generator())
