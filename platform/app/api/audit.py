from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.database import get_db
from app.models.audit import AuditLog
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.job import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=ApiResponse[list[AuditLogOut]])
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.audit"))],
    limit: int = Query(100, ge=1, le=500),
) -> ApiResponse[list[AuditLogOut]]:
    logs = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return ApiResponse(data=[AuditLogOut.model_validate(log) for log in logs])
