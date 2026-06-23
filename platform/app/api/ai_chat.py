"""AI 首页对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.api.streaming_utils import stream_sse_payloads
from app.database import get_db
from app.models.org import User
from app.schemas.ai_chat import (
    AiChatRequest,
    AiChatResponse,
    AttachmentSessionOut,
    AttachmentUploadOut,
)
from app.schemas.agent_skill import AgentSkillCatalogItemOut
from app.schemas.agent_skill import AgentMemoryOut, AgentMemoryUpdateIn
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


@router.get("/skills/catalog", response_model=ApiResponse[list[AgentSkillCatalogItemOut]])
def read_ai_chat_skill_catalog(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AgentSkillCatalogItemOut]]:
    """当前用户可见的 Agent Skills 目录（Discovery）。"""
    from app.services.skill_chat_service import get_user_skill_catalog

    return ApiResponse(data=get_user_skill_catalog(db, user))


@router.get("/agent-memory", response_model=ApiResponse[AgentMemoryOut])
def read_agent_memory(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AgentMemoryOut]:
    from app.services.agent_memory_service import read_user_memory

    return ApiResponse(data=AgentMemoryOut(content=read_user_memory(user.id)))


@router.put("/agent-memory", response_model=ApiResponse[AgentMemoryOut])
def write_agent_memory(
    body: AgentMemoryUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AgentMemoryOut]:
    from app.core.exceptions import bad_request
    from app.services.agent_memory_service import read_user_memory, write_user_memory

    if not write_user_memory(user.id, body.content):
        raise bad_request("记忆保存失败")
    return ApiResponse(data=AgentMemoryOut(content=read_user_memory(user.id)))


@router.delete("/agent-memory", response_model=ApiResponse[None])
def clear_agent_memory(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    from app.services.agent_memory_service import clear_user_memory

    clear_user_memory(user.id)
    return ApiResponse(data=None)


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
    user_id = user.id

    async def payloads():
        async for payload in iter_chat_with_ai_agent_stream(
            user_id=user_id,
            message=body.message,
            history=body.history,
            conversation_id=body.conversation_id,
            attachment_session_id=body.attachment_session_id,
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
