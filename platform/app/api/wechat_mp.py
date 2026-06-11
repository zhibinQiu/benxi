"""微信公众号资讯 — 跟踪列表与推文汇总。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.wechat_mp import (
    WechatMpArticleDetailOut,
    WechatMpArticleOut,
    WechatMpImportIn,
    WechatMpImportOut,
    WechatMpParseUrlIn,
    WechatMpParseUrlOut,
    WechatMpSourceCreate,
    WechatMpSourceOut,
    WechatMpSyncOut,
)
from app.services import wechat_mp_service as svc

router = APIRouter(
    prefix="/wechat-mp",
    tags=["wechat-mp"],
    dependencies=[Depends(require_feature("wechat_mp_feed"))],
)


@router.post("/parse-url", response_model=ApiResponse[WechatMpParseUrlOut])
def parse_article_url(
    body: WechatMpParseUrlIn,
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[WechatMpParseUrlOut]:
    parsed = svc.parse_url(body.url)
    return ApiResponse(
        data=WechatMpParseUrlOut(
            title=parsed.title,
            summary=parsed.summary,
            cover_url=parsed.cover_url,
            author=parsed.author,
            biz=parsed.biz,
            account_name=parsed.account_name,
            original_url=parsed.original_url,
            publish_at=parsed.publish_at,
        )
    )


@router.get("/sources", response_model=ApiResponse[list[WechatMpSourceOut]])
def list_sources(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[WechatMpSourceOut]]:
    rows = svc.list_user_sources(db, user)
    return ApiResponse(data=[WechatMpSourceOut.model_validate(r) for r in rows])


@router.post("/sources", response_model=ApiResponse[WechatMpSourceOut])
def create_source(
    body: WechatMpSourceCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[WechatMpSourceOut]:
    row = svc.subscribe_source(
        db,
        user,
        name=body.name.strip(),
        sample_url=body.sample_url,
        biz=body.biz,
    )
    db.commit()
    return ApiResponse(data=WechatMpSourceOut.model_validate(row))


@router.delete("/sources/{source_id}", response_model=ApiResponse[dict])
def delete_source(
    source_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    svc.unsubscribe_source(db, user, source_id)
    db.commit()
    return ApiResponse(data={"ok": True})


@router.post("/sources/{source_id}/sync", response_model=ApiResponse[WechatMpSyncOut])
def sync_source(
    source_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[WechatMpSyncOut]:
    result = svc.sync_source(db, user, source_id)
    db.commit()
    return ApiResponse(data=WechatMpSyncOut.model_validate(result))


@router.get("/articles", response_model=ApiResponse[PageResult[WechatMpArticleOut]])
def list_articles(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    source_id: uuid.UUID | None = None,
) -> ApiResponse[PageResult[WechatMpArticleOut]]:
    items, total = svc.list_articles(
        db, user, source_id=source_id, page=page, page_size=page_size
    )
    return ApiResponse(
        data=PageResult(
            items=[WechatMpArticleOut.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/articles/{article_id}",
    response_model=ApiResponse[WechatMpArticleDetailOut],
)
def get_article(
    article_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[WechatMpArticleDetailOut]:
    data = svc.get_article_detail(db, user, article_id)
    return ApiResponse(data=WechatMpArticleDetailOut.model_validate(data))


@router.post(
    "/articles/ingest-url",
    response_model=ApiResponse[WechatMpArticleDetailOut],
)
def ingest_url(
    body: WechatMpParseUrlIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[WechatMpArticleDetailOut]:
    data = svc.ingest_url(db, user, body.url)
    db.commit()
    return ApiResponse(data=WechatMpArticleDetailOut.model_validate(data))


@router.post(
    "/articles/{article_id}/import",
    response_model=ApiResponse[WechatMpImportOut],
)
def import_article(
    article_id: uuid.UUID,
    body: WechatMpImportIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[WechatMpImportOut]:
    data = svc.import_article_to_document(
        db,
        user,
        article_id,
        scope=body.scope,
        dept_id=body.dept_id,
        sync_knowflow=body.sync_knowflow,
    )
    db.commit()
    return ApiResponse(data=WechatMpImportOut.model_validate(data))
