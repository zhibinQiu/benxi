"""碳新闻 API：实时爬取 + 基于当次结果的一问一答。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_feature
from app.models.org import User
from app.schemas.carbon_news import (
    CarbonNewsAskIn,
    CarbonNewsAskOut,
    CarbonNewsCrawlIn,
    CarbonNewsCrawlOut,
)
from app.schemas.common import ApiResponse
from app.services import carbon_news_service as svc

router = APIRouter(
    prefix="/carbon-news",
    tags=["carbon-news"],
    dependencies=[Depends(require_feature("carbon_news"))],
)


@router.post("/crawl", response_model=ApiResponse[CarbonNewsCrawlOut])
async def crawl_carbon_news(
    body: CarbonNewsCrawlIn,
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CarbonNewsCrawlOut]:
    try:
        data = await svc.crawl_carbon_news(
            keyword=body.keyword,
            limit=body.limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"爬取失败：{exc}") from exc
    return ApiResponse(data=data)


@router.post("/ask", response_model=ApiResponse[CarbonNewsAskOut])
async def ask_carbon_news(
    body: CarbonNewsAskIn,
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CarbonNewsAskOut]:
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")
    data = await svc.ask_carbon_news(question=question, items=list(body.items or []))
    return ApiResponse(data=data)
