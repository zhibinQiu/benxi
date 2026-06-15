"""PageIndex 实验性检索 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.pageindex import (
    PageindexMetaOut,
    PageindexSearchOut,
    PageindexSearchRequest,
)
from app.services import pageindex_service as svc

router = APIRouter(
    prefix="/pageindex",
    tags=["pageindex"],
    dependencies=[Depends(require_feature("pageindex_demo"))],
)


@router.get("/meta", response_model=ApiResponse[PageindexMetaOut])
def pageindex_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[PageindexMetaOut]:
    return ApiResponse(data=PageindexMetaOut.model_validate(svc.get_meta()))


@router.post("/search", response_model=ApiResponse[PageindexSearchOut])
def pageindex_search(
    body: PageindexSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[PageindexSearchOut]:
    data = svc.search_with_pageindex(
        db,
        user,
        question=body.question,
        document_ids=body.document_ids,
    )
    return ApiResponse(data=PageindexSearchOut.model_validate(data))


@router.post("/search/stream")
async def pageindex_search_stream(
    body: PageindexSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    from sse_starlette.sse import EventSourceResponse

    async def event_gen():
        async for chunk in svc.iter_pageindex_search_stream(
            db,
            user,
            question=body.question,
            document_ids=body.document_ids,
        ):
            yield {"data": chunk}

    return EventSourceResponse(event_gen())
