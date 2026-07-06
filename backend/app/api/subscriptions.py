"""统一资讯订阅：手动链接收录。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_any_permission
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.subscription import (
    SubscriptionImportIn,
    SubscriptionImportOut,
    SubscriptionIngestIn,
    SubscriptionItemDetailOut,
    SubscriptionItemOut,
)
from app.services import subscription_service as svc

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"],
    dependencies=[
        Depends(
            require_any_permission(
                "feature.subscriptions",
                "feature.wechat_mp_feed",
            )
        )
    ],
)


@router.post("/ingest-url", response_model=ApiResponse[SubscriptionItemDetailOut])
def ingest_url(
    body: SubscriptionIngestIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[SubscriptionItemDetailOut]:
    data = svc.ingest_url(db, user, body.url.strip())
    db.commit()
    return ApiResponse(data=SubscriptionItemDetailOut.model_validate(data))


@router.get("/items", response_model=ApiResponse[PageResult[SubscriptionItemOut]])
def list_items(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    keyword: str | None = Query(None, max_length=200),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    all_users: bool = Query(False),
) -> ApiResponse[PageResult[SubscriptionItemOut]]:
    items, total = svc.list_items(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
        all_users=all_users,
    )
    return ApiResponse(
        data=PageResult(
            items=[SubscriptionItemOut.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/items/{ref}", response_model=ApiResponse[SubscriptionItemDetailOut])
def get_item(
    ref: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[SubscriptionItemDetailOut]:
    data = svc.get_item_detail(db, user, ref)
    return ApiResponse(data=SubscriptionItemDetailOut.model_validate(data))


@router.post("/items/{ref}/import", response_model=ApiResponse[SubscriptionImportOut])
def import_item(
    ref: str,
    body: SubscriptionImportIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[SubscriptionImportOut]:
    data = svc.import_item_to_document(
        db, user, ref, sync_knowflow=body.sync_knowflow
    )
    db.commit()
    return ApiResponse(data=SubscriptionImportOut.model_validate(data))


@router.delete("/items/{ref}", response_model=ApiResponse[dict])
def delete_item(
    ref: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    data = svc.delete_item(db, user, ref)
    db.commit()
    return ApiResponse(data=data)
