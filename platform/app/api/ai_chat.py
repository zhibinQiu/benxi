"""AI 首页对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.ai_chat import (
    AiChatRequest,
    AiChatResponse,
    AttachmentSessionOut,
    AttachmentUploadOut,
)
from app.schemas.common import ApiResponse
from app.services import ai_chat_attachment_service as attachment_svc
from app.services.ai_chat_service import chat_with_ai_agent, iter_chat_with_ai_agent_stream

router = APIRouter(
    prefix="/ai-chat",
    tags=["ai-chat"],
    dependencies=[Depends(require_feature("ai_home"))],
)


@router.post("/attachments/upload", response_model=ApiResponse[AttachmentUploadOut])
async def upload_ai_chat_attachments(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    files: list[UploadFile] = File(..., description="临时附件，可多个"),
    attachment_session_id: str | None = Form(None),
) -> ApiResponse[AttachmentUploadOut]:
    result = await attachment_svc.upload_attachments(
        db,
        user_id=user.id,
        files=files,
        attachment_session_id=attachment_session_id,
    )
    return ApiResponse(data=result)


@router.get(
    "/attachments/{attachment_session_id}",
    response_model=ApiResponse[AttachmentSessionOut],
)
def get_ai_chat_attachments(
    attachment_session_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AttachmentSessionOut]:
    return ApiResponse(
        data=attachment_svc.get_session_out(user.id, attachment_session_id)
    )


@router.delete("/attachments/{attachment_session_id}")
def clear_ai_chat_attachments(
    attachment_session_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    attachment_svc.clear_attachment_session(user.id, attachment_session_id)
    return ApiResponse(data={"ok": True})


@router.delete(
    "/attachments/{attachment_session_id}/files/{file_id}",
    response_model=ApiResponse[AttachmentSessionOut],
)
def remove_ai_chat_attachment_file(
    attachment_session_id: str,
    file_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AttachmentSessionOut]:
    return ApiResponse(
        data=attachment_svc.remove_attachment_file(
            user.id, attachment_session_id, file_id
        )
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
        user=user,
        conversation_id=body.conversation_id,
        attachment_session_id=body.attachment_session_id,
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
            user=user,
            conversation_id=body.conversation_id,
            attachment_session_id=body.attachment_session_id,
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
