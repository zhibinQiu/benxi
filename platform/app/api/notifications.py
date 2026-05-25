from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.job import NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=ApiResponse[PageResult[NotificationOut]])
def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
) -> ApiResponse[PageResult[NotificationOut]]:
    items, total = notification_service.list_notifications(
        db, user.id, page=page, page_size=page_size, unread_only=unread_only
    )
    return ApiResponse(
        data=PageResult(
            items=[NotificationOut.model_validate(n) for n in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.patch("/read-all", response_model=ApiResponse[dict])
def mark_all_read(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    updated = notification_service.mark_all_read(db, user.id)
    return ApiResponse(data={"updated": updated})


@router.delete("/clear", response_model=ApiResponse[dict])
def clear_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    scope: str = Query("read", pattern="^(read|all)$"),
) -> ApiResponse[dict]:
    deleted = notification_service.clear_notifications(db, user.id, scope=scope)
    return ApiResponse(data={"deleted": deleted, "scope": scope})


@router.patch("/{notification_id}/read", response_model=ApiResponse[None])
def mark_read(
    notification_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    from app.models.notification import Notification

    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise not_found()
    notification_service.mark_read(db, user.id, notification_id)
    return ApiResponse()
