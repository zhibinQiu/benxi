"""智能问数 v2 — 对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.api.streaming_utils import stream_sse_payloads
from app.database import get_db
from app.models.org import User
from app.schemas.ai_chat import AiChatRequest, AiChatResponse
from app.schemas.common import ApiResponse
from app.services.smart_data_query_v2_service import (
    chat_smart_data_query_v2,
    iter_smart_data_query_v2_stream,
    meta,
)

router = APIRouter(
    prefix="/smart-data-query",
    tags=["smart-data-query"],
    dependencies=[Depends(require_feature("smart_data_query"))],
)


@router.get("/meta", response_model=ApiResponse[dict])
async def smart_data_query_v2_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    return ApiResponse(data=meta())


@router.post("/chat", response_model=ApiResponse[AiChatResponse])
async def smart_data_query_v2_chat(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AiChatResponse]:
    result = await chat_smart_data_query_v2(
        message=body.message,
        user_id=str(user.id),
        conversation_id=body.conversation_id,
    )
    return ApiResponse(data=AiChatResponse.model_validate(result))


@router.post("/chat/stream")
async def smart_data_query_v2_chat_stream(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    async def payloads():
        async for payload in iter_smart_data_query_v2_stream(
            message=body.message,
            user_id=str(user.id),
            conversation_id=body.conversation_id,
        ):
            yield payload

    return StreamingResponse(
        stream_sse_payloads(db, payloads),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
