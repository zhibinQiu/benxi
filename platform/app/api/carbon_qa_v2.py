"""双碳问答 v2 — 对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.models.org import User
from app.schemas.ai_chat import AiChatRequest, AiChatResponse
from app.schemas.common import ApiResponse
from app.services.carbon_qa_v2_service import (
    chat_carbon_qa_v2,
    iter_carbon_qa_v2_stream,
    meta,
)

router = APIRouter(
    prefix="/carbon-qa",
    tags=["carbon-qa"],
    dependencies=[Depends(require_feature("carbon_qa"))],
)


@router.get("/meta", response_model=ApiResponse[dict])
async def carbon_qa_v2_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    return ApiResponse(data=meta())


@router.post("/chat", response_model=ApiResponse[AiChatResponse])
async def carbon_qa_v2_chat(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AiChatResponse]:
    result = await chat_carbon_qa_v2(
        message=body.message,
        user_id=str(user.id),
        conversation_id=body.conversation_id,
    )
    return ApiResponse(data=AiChatResponse.model_validate(result))


@router.post("/chat/stream")
async def carbon_qa_v2_chat_stream(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    async def sse_body():
        async for payload in iter_carbon_qa_v2_stream(
            message=body.message,
            user_id=str(user.id),
            conversation_id=body.conversation_id,
        ):
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        sse_body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
