from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.audit import AuditLog
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.monitor import AuditLogItemOut, SystemMetricsOut
from app.services.knowflow_queue_service import collect_knowflow_queue_metrics
from app.services.system_monitor import collect_system_metrics

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/metrics", response_model=ApiResponse[SystemMetricsOut])
def get_system_metrics(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SystemMetricsOut]:
    payload = collect_system_metrics()
    payload["knowflow_queue"] = collect_knowflow_queue_metrics(db)
    return ApiResponse(data=SystemMetricsOut.model_validate(payload))


@router.get("/audit-logs", response_model=ApiResponse[list[AuditLogItemOut]])
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    limit: int = Query(100, ge=1, le=500),
) -> ApiResponse[list[AuditLogItemOut]]:
    logs = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    user_ids = {log.user_id for log in logs if log.user_id}
    names: dict = {}
    if user_ids:
        users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
        names = {u.id: u.username for u in users}
    return ApiResponse(
        data=[
            AuditLogItemOut(
                id=log.id,
                user_id=log.user_id,
                username=names.get(log.user_id) if log.user_id else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                detail=log.detail,
                created_at=log.created_at,
            )
            for log in logs
        ]
    )
