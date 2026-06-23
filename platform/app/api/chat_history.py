"""对话历史 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import bad_request, forbidden
from app.core.permissions import user_has_permission
from app.database import get_db
from app.features.registry import get_plugin
from app.models.org import User
from app.schemas.common import ApiResponse
from app.services import chat_history_service

router = APIRouter(prefix="/chat-history", tags=["chat-history"])

_SCOPE_FEATURES = {
    "ai-home": "ai_home",
    "carbon-qa": "carbon_qa",
    "smart-data-query": "smart_data_query",
    "report-generation": "report_generation",
}


def _ensure_scope_access(db: Session, user: User, scope: str) -> None:
    if scope not in chat_history_service.CHAT_SCOPES:
        raise bad_request("不支持的对话类型")
    feature_id = _SCOPE_FEATURES.get(scope)
    if not feature_id:
        return
    plugin = get_plugin(feature_id)
    if not plugin:
        raise bad_request("不支持的对话类型")
    if not user_has_permission(db, user, plugin.permission_code):
        raise forbidden(f"Missing permission: {plugin.permission_code}")


@router.get("/{scope}/conversations", response_model=ApiResponse[list[dict]])
async def list_chat_conversations(
    scope: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(30, ge=1, le=100),
) -> ApiResponse[list[dict]]:
    _ensure_scope_access(db, user, scope)
    rows = await chat_history_service.list_conversations(
        db, user_id=user.id, scope=scope, limit=limit
    )
    return ApiResponse(data=rows)


@router.get(
    "/{scope}/conversations/{conversation_id}/messages",
    response_model=ApiResponse[dict],
)
async def list_chat_messages(
    scope: str,
    conversation_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(48, ge=1, le=100),
    before_id: str | None = Query(None),
) -> ApiResponse[dict]:
    _ensure_scope_access(db, user, scope)
    payload = await chat_history_service.list_messages(
        db,
        user_id=user.id,
        scope=scope,
        conversation_id=conversation_id,
        limit=limit,
        before_id=before_id,
    )
    return ApiResponse(data=payload)


@router.delete("/{scope}/conversations", response_model=ApiResponse[dict])
async def clear_chat_conversations(
    scope: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    _ensure_scope_access(db, user, scope)
    deleted = await chat_history_service.clear_conversations(
        db, user_id=user.id, scope=scope
    )
    return ApiResponse(data={"ok": True, "deleted": deleted})


@router.delete(
    "/{scope}/conversations/{conversation_id}",
    response_model=ApiResponse[dict],
)
async def delete_chat_conversation(
    scope: str,
    conversation_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    _ensure_scope_access(db, user, scope)
    await chat_history_service.delete_conversation(
        db,
        user_id=user.id,
        scope=scope,
        conversation_id=conversation_id,
    )
    return ApiResponse(data={"ok": True})
