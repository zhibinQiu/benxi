"""提示词管理 API — 增删改查。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.prompt import PromptCreate, PromptOut, PromptUpdate
from app.services import prompt_service as svc

router = APIRouter(
    prefix="/prompts",
    tags=["prompts"],
    dependencies=[Depends(require_feature("prompt_management"))],
)


@router.get("", response_model=ApiResponse)
def list_prompts(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    category: str | None = Query(None, description="按分类筛选"),
    search: str | None = Query(None, description="模糊搜索标题/内容"),
) -> ApiResponse:
    """获取提示词列表。"""
    items = svc.list_prompts(db, user.id, category=category, search=search)
    return ApiResponse(data=[PromptOut.model_validate(i) for i in items])


@router.get("/categories/summary", response_model=ApiResponse)
def list_categories(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """获取分类统计。"""
    cats = svc.list_categories(db, user.id)
    return ApiResponse(data=[c.model_dump() for c in cats])


@router.get("/{prompt_id}", response_model=ApiResponse)
def get_prompt(
    prompt_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """获取单条提示词。"""
    item = svc.get_prompt(db, user.id, prompt_id)
    if not item:
        return ApiResponse(code=404, message="提示词不存在")
    return ApiResponse(data=PromptOut.model_validate(item))


@router.post("", response_model=ApiResponse)
def create_prompt(
    body: PromptCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """创建提示词。"""
    item = svc.create_prompt(db, user.id, body)
    return ApiResponse(data=PromptOut.model_validate(item))


@router.put("/{prompt_id}", response_model=ApiResponse)
def update_prompt(
    prompt_id: uuid.UUID,
    body: PromptUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """更新提示词。"""
    item = svc.update_prompt(db, user.id, prompt_id, body)
    if not item:
        return ApiResponse(code=404, message="提示词不存在")
    return ApiResponse(data=PromptOut.model_validate(item))


@router.delete("/{prompt_id}", response_model=ApiResponse)
def delete_prompt(
    prompt_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """删除提示词。"""
    ok = svc.delete_prompt(db, user.id, prompt_id)
    return ApiResponse(data={"deleted": ok})
