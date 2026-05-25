"""智能问数 — 内嵌设计系统页面。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_feature
from app.models.org import User
from app.schemas.common import ApiResponse
from app.services.feature_embed_urls import resolve_smart_data_query_embed_url

router = APIRouter(
    prefix="/smart-data-query",
    tags=["smart-data-query"],
    dependencies=[Depends(require_feature("smart_data_query"))],
)


@router.get("/meta")
async def smart_data_query_meta(
    _user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    url = resolve_smart_data_query_embed_url()
    return ApiResponse(
        data={
            "embed_url": url,
            "available": bool(url),
        }
    )
