"""RSS / 网站资讯订阅 API。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.feed_subscription import (
    FeedEntryDetailOut,
    FeedEntryOut,
    FeedImportIn,
    FeedImportOut,
    FeedPresetOut,
    FeedSourceCreate,
    FeedSourceOut,
    FeedSyncOut,
)
from app.services import feed_subscription_service as svc
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/feed-subscriptions",
    tags=["feed-subscriptions"],
    dependencies=[Depends(require_feature("feed_subscriptions"))],
)


@router.get("/presets", response_model=ApiResponse[list[FeedPresetOut]])
def list_presets(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[FeedPresetOut]]:
    return ApiResponse(
        data=[FeedPresetOut.model_validate(p) for p in svc.list_presets()]
    )


@router.get("/sources", response_model=ApiResponse[list[FeedSourceOut]])
def list_sources(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    kind: str | None = Query(None, pattern="^(rss|website)$"),
) -> ApiResponse[list[FeedSourceOut]]:
    rows = svc.list_user_sources(db, user, kind=kind)
    return ApiResponse(data=[FeedSourceOut.model_validate(r) for r in rows])


@router.post("/sources", response_model=ApiResponse[FeedSourceOut])
def create_source(
    body: FeedSourceCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[FeedSourceOut]:
    row = svc.subscribe_source(
        db,
        user,
        name=body.name.strip(),
        feed_url=body.feed_url.strip(),
        kind=body.kind,
        category=(body.category or "").strip(),
    )
    db.commit()
    return ApiResponse(data=FeedSourceOut.model_validate(row))


@router.post("/presets/{index}", response_model=ApiResponse[FeedSourceOut])
def subscribe_preset(
    index: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[FeedSourceOut]:
    row = svc.subscribe_preset(db, user, index)
    db.commit()
    return ApiResponse(data=FeedSourceOut.model_validate(row))


@router.delete("/sources/{source_id}", response_model=ApiResponse[dict])
def delete_source(
    source_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    svc.unsubscribe_source(db, user, source_id)
    db.commit()
    return ApiResponse(data={"ok": True})


@router.post("/sources/{source_id}/sync", response_model=ApiResponse[FeedSyncOut])
def sync_source(
    source_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[FeedSyncOut]:
    result = svc.sync_source(db, user, source_id)
    db.commit()
    return ApiResponse(data=FeedSyncOut.model_validate(result))


@router.get("/entries", response_model=ApiResponse[PageResult[FeedEntryOut]])
def list_entries(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    source_id: uuid.UUID | None = None,
    kind: str | None = Query(None, pattern="^(rss|website)$"),
) -> ApiResponse[PageResult[FeedEntryOut]]:
    items, total = svc.list_entries(
        db, user, source_id=source_id, kind=kind, page=page, page_size=page_size
    )
    return ApiResponse(
        data=PageResult(
            items=[FeedEntryOut.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/entries/{entry_id}", response_model=ApiResponse[FeedEntryDetailOut])
def get_entry(
    entry_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[FeedEntryDetailOut]:
    data = svc.get_entry_detail(db, user, entry_id)
    return ApiResponse(data=FeedEntryDetailOut.model_validate(data))


@router.post("/entries/{entry_id}/import", response_model=ApiResponse[FeedImportOut])
def import_entry(
    entry_id: uuid.UUID,
    body: FeedImportIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[FeedImportOut]:
    data = svc.import_entry_to_document(
        db,
        user,
        entry_id,
        scope=body.scope,
        dept_id=body.dept_id,
        sync_knowflow=body.sync_knowflow,
    )
    db.commit()
    return ApiResponse(data=FeedImportOut.model_validate(data))
