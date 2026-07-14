"""AI 首页对话 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
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
    ModelProviderItem,
)
from app.schemas.agent_profile import AgentCatalogItemOut
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


@router.get("/agents/catalog", response_model=ApiResponse[list[AgentCatalogItemOut]])
def read_ai_chat_agent_catalog(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AgentCatalogItemOut]]:
    """本析智能对话：可选专精智能体目录。"""
    from app.services import agent_profile_service as agent_profile_svc

    return ApiResponse(data=agent_profile_svc.list_user_agent_catalog(db))


@router.get("/agent-memory", response_model=ApiResponse[AgentMemoryOut])
def read_agent_memory(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AgentMemoryOut]:
    from app.services.agent_memory_service import MEMORY_TEMPLATE, read_user_memory

    content = read_user_memory(user.id)
    if not content:
        content = MEMORY_TEMPLATE
    return ApiResponse(data=AgentMemoryOut(content=content))


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


@router.get("/model-providers", response_model=ApiResponse[list[ModelProviderItem]])
def list_ai_chat_model_providers(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[ModelProviderItem]]:
    """面向 AI 对话的模型提供商列表（不含密钥），用于输入框模型切换。"""
    from app.services.model_settings_service import get_effective_model_config

    merged = get_effective_model_config(db)
    items: list[ModelProviderItem] = []

    for prefix, rtype in (("llm", "llm"), ("multimodal", "multimodal")):
        providers_key = f"{prefix}_providers"
        active_key = f"{prefix}_active_provider"
        raw = merged.get(providers_key, "")
        if raw:
            import json

            try:
                providers = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                providers = None
            if isinstance(providers, list):
                active_id = merged.get(active_key, "")
                for p in providers:
                    pid = p.get("id", "")
                    label = p.get("label", "") or p.get("model_name", "") or ""
                    model_name = p.get("model_name", "") or ""
                    items.append(
                        ModelProviderItem(id=pid, label=label, model_name=model_name, resource_type=rtype)
                    )
                continue

        # 无 providers 数组时，从 flat 字段构造默认项（兼容旧配置）
        base_url = (merged.get(f"{prefix}_base_url") or "").strip()
        api_key = (merged.get(f"{prefix}_api_key") or "").strip()
        model_name = (merged.get(f"{prefix}_model") or "").strip()
        if base_url and api_key and model_name:
            display = model_name
            items.append(
                ModelProviderItem(
                    id=f"__flat__{prefix}",
                    label=display,
                    model_name=model_name,
                    resource_type=rtype,
                )
            )

    return ApiResponse(data=items)


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
        model_provider_id=body.model_provider_id,
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
            model_provider_id=body.model_provider_id,
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


class _ToolConfirmRequest(BaseModel):
    accepted: bool


class _ToolChoiceRequest(BaseModel):
    choice: str = Field(min_length=1, max_length=500)


@router.post("/chat/tools/{confirmation_id}/confirm")
def confirm_tool_execution(
    confirmation_id: str,
    body: _ToolConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """用户确认或拒绝工具执行。

    SSE 流中，Agent 发出 confirmation_required 事件后，
    前端通过此端点将用户选择通知后端的轮询循环。
    """
    from app.core.exceptions import bad_request, forbidden
    from app.core.human_in_the_loop import confirm_key as _get_key
    from app.core.redis_client import get_redis_client as _get_redis

    client = _get_redis()
    if not client:
        raise bad_request("Redis 不可用，无法处理工具确认")
    key = _get_key(confirmation_id)
    stored_user_id = client.hget(key, "user_id")
    if not stored_user_id:
        raise bad_request("确认请求已过期或不存在")
    if stored_user_id != str(user.id):
        raise forbidden("无权操作此确认请求")
    response = "accepted" if body.accepted else "rejected"
    existing = client.hget(key, "response")
    if existing == "accepted":
        return ApiResponse(code=0, message="已确认，无需重复操作")
    if existing == "rejected":
        return ApiResponse(code=0, message="已拒绝，无需重复操作")
    set_confirm_response(confirmation_id, response)
    return ApiResponse(code=0, message="操作成功" if body.accepted else "已取消")


@router.post("/chat/tools/{choice_id}/choose")
def choose_tool_option(
    choice_id: str,
    body: _ToolChoiceRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """用户在 Agent 提供的多个方案中选择一个。

    SSE 流中，Agent 发出 choice_required 事件后，
    前端通过此端点将用户的选择通知后端的轮询循环。
    """
    from app.core.exceptions import bad_request, forbidden
    from app.core.human_in_the_loop import choice_key as _choice_key
    from app.core.human_in_the_loop import get_choice_options, set_choice_response
    from app.core.redis_client import get_redis_client as _get_redis

    client = _get_redis()
    if not client:
        raise bad_request("Redis 不可用，无法处理方案选择")
    key = _choice_key(choice_id)
    stored_user_id = client.hget(key, "user_id")
    if not stored_user_id:
        raise bad_request("方案选择已过期或不存在")
    if stored_user_id != str(user.id):
        raise forbidden("无权操作此方案选择")
    existing = client.hget(key, "response")
    if existing:
        return ApiResponse(code=0, message="已选择，无需重复操作")
    # 校验选项是否在有效列表中
    options = get_choice_options(choice_id)
    if options and body.choice not in options:
        raise bad_request(f"无效选项「{body.choice}」，有效选项：{', '.join(options)}")
    if not set_choice_response(choice_id, body.choice):
        raise bad_request("方案选择失败，请重试")
    return ApiResponse(code=0, message=f"已选择：{body.choice}")


# ── Checkpoint 恢复 ──


class _ResumeCheckpointRequest(BaseModel):
    """恢复 checkpoint 时附带用户选择。"""

    accepted: bool | None = None  # 确认操作时使用
    choice: str | None = None  # 方案选择时使用


@router.get("/checkpoints/pending")
def list_pending_checkpoints(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[dict]]:
    """获取当前用户所有待处理的 checkpoint。"""
    from app.core.agent_checkpoint import get_pending_checkpoints_for_user

    checkpoints = get_pending_checkpoints_for_user(str(user.id))
    return ApiResponse(data=checkpoints)


@router.get("/checkpoints/{checkpoint_id}")
def get_checkpoint_status(
    checkpoint_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """查询 checkpoint 状态。"""
    from app.core.agent_checkpoint import load_checkpoint
    from app.core.exceptions import bad_request, forbidden

    cp = load_checkpoint(checkpoint_id)
    if not cp:
        raise bad_request("Checkpoint 已过期或不存在")

    if str(cp.get("user_id", "")) != str(user.id):
        raise forbidden("无权访问此 checkpoint")

    pending = cp.get("pending_data") or {}
    phase = cp.get("phase", "")
    if phase == "awaiting_confirmation":
        confirmation_id = pending.get("confirmation_id", "")
        from app.core.human_in_the_loop import get_confirm_response

        response = get_confirm_response(confirmation_id) if confirmation_id else None
    elif phase == "awaiting_choice":
        choice_id = pending.get("choice_id", "")
        from app.core.human_in_the_loop import get_choice_response

        response = get_choice_response(choice_id) if choice_id else None
    else:
        response = None

    return ApiResponse(data={
        "phase": phase,
        "has_response": response is not None,
        "response": response,
        "pending_data": pending,
    })


@router.post("/checkpoints/{checkpoint_id}/resume")
def resume_from_checkpoint(
    checkpoint_id: str,
    body: _ResumeCheckpointRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """从 checkpoint 恢复 Agent 执行。

    用户对之前中断的操作做出确认/选择后，通过此端点建立新的 SSE 流，
    从 checkpoint 保存的状态继续执行。
    """
    from app.core.agent_checkpoint import load_checkpoint
    from app.core.exceptions import bad_request, forbidden
    from app.services.ai_chat_checkpoint import iter_resumed_agent_stream

    cp = load_checkpoint(checkpoint_id)
    if not cp:
        raise bad_request("Checkpoint 已过期或不存在，请重新发送消息")

    if str(cp.get("user_id", "")) != str(user.id):
        raise forbidden("无权操作此 checkpoint")

    phase = cp.get("phase", "")
    # 写入用户响应到 Redis（如果是确认/拒绝/选择）
    if phase == "awaiting_confirmation" and body.accepted is not None:
        from app.core.human_in_the_loop import (
            get_confirm_response,
            set_confirm_response,
        )

        existing = get_confirm_response(
            (cp.get("pending_data") or {}).get("confirmation_id", "")
        )
        if not existing:
            set_confirm_response(
                (cp.get("pending_data") or {}).get("confirmation_id", ""),
                "accepted" if body.accepted else "rejected",
            )
    elif phase == "awaiting_choice" and body.choice:
        from app.core.human_in_the_loop import set_choice_response

        pending = cp.get("pending_data") or {}
        choice_id = pending.get("choice_id", "")
        if choice_id:
            options_raw = pending.get("options", "[]")
            import json

            options = json.loads(options_raw) if isinstance(options_raw, str) else options_raw
            if isinstance(options, list) and body.choice not in options:
                raise bad_request(
                    f"无效选项「{body.choice}」，有效选项：{', '.join(options)}"
                )
            set_choice_response(choice_id, body.choice)

    return StreamingResponse(
        stream_sse_payloads(
            db,
            iter_resumed_agent_stream(
                user_id=user.id,
                checkpoint_id=checkpoint_id,
                conversation_id=None,
            ),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
