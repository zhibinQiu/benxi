"""AI 首页对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.ai_chat import AiChatRequest, AiChatResponse
from app.schemas.common import ApiResponse
from app.services.ai_chat_service import chat_with_ai_agent, iter_chat_with_ai_agent_stream

router = APIRouter(
    prefix="/ai-chat",
    tags=["ai-chat"],
    dependencies=[Depends(require_feature("ai_home"))],
)


@router.post("/chat", response_model=ApiResponse[AiChatResponse])
async def ai_home_chat(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AiChatResponse]:
    result = await chat_with_ai_agent(
        message=body.message,
        history=body.history,
        db=db,
        user_id=user.id,
        conversation_id=body.conversation_id,
    )
    return ApiResponse(data=AiChatResponse.model_validate(result))


@router.post("/chat/stream")
async def ai_home_chat_stream(
    body: AiChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    async def sse_body():
        async for payload in iter_chat_with_ai_agent_stream(
            message=body.message,
            history=body.history,
            db=db,
            user_id=user.id,
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
