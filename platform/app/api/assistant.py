"""智能客服 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import User
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.schemas.common import ApiResponse
from app.services.assistant_service import chat_with_assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ApiResponse[AssistantChatResponse])
async def assistant_chat(
    body: AssistantChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AssistantChatResponse]:
    result = await chat_with_assistant(
        db,
        user,
        message=body.message,
        history=body.history,
        page_hint=body.page_hint,
    )
    return ApiResponse(data=AssistantChatResponse.model_validate(result))
