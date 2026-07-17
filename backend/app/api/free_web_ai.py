"""免费网页 AI API 路由。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user as get_current_active_user
from app.integrations.free_web_ai import get_free_web_ai_manager
from app.models.org import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/free-web-ai", tags=["free_web_ai"])


# ── Request/Response models ──


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000, description="提示词")
    provider: str | None = Field(default=None, description="指定 provider: doubao/qwen/deepseek")
    timeout_ms: int | None = Field(default=None, ge=10000, le=600000)


class ImageGenRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000, description="生图描述")
    provider: str | None = Field(default=None, description="指定 provider: doubao/qwen")


class ImageAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000, description="关于图片的问题")
    image_path: str = Field(min_length=1, description="图片文件路径（服务器本地路径）")
    provider: str | None = Field(default=None, description="指定 provider")


class WebAiResponse(BaseModel):
    success: bool
    response: str | None = None
    provider: str | None = None
    reason: str | None = None
    reasons: dict[str, str] | None = None


# ── API endpoints ──


@router.post("/chat", response_model=WebAiResponse)
async def free_web_ai_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_active_user),
) -> WebAiResponse:
    """免费网页 AI 文本对话（自动 fallback 或指定 provider）。"""
    _require_permission(current_user)
    mgr = get_free_web_ai_manager()
    result = await mgr.chat(req.prompt, provider=req.provider, timeout_ms=req.timeout_ms)
    return WebAiResponse(
        success=result.get("success", False),
        response=result.get("response"),
        provider=result.get("provider"),
        reason=result.get("reason"),
        reasons=result.get("reasons"),
    )


@router.post("/image", response_model=WebAiResponse)
async def free_web_ai_image(
    req: ImageGenRequest,
    current_user: User = Depends(get_current_active_user),
) -> WebAiResponse:
    """文字生图（豆包/千问）。"""
    _require_permission(current_user)
    mgr = get_free_web_ai_manager()
    result = await mgr.generate_image(req.prompt, provider=req.provider)
    return WebAiResponse(
        success=result.get("success", False),
        response=result.get("response"),
        provider=result.get("provider"),
        reason=result.get("reason"),
        reasons=result.get("reasons"),
    )


@router.post("/ask", response_model=WebAiResponse)
async def free_web_ai_ask(
    req: ImageAskRequest,
    current_user: User = Depends(get_current_active_user),
) -> WebAiResponse:
    """识图问答 — 上传图片并提问。"""
    _require_permission(current_user)
    import os
    if not os.path.isfile(req.image_path):
        raise HTTPException(status_code=400, detail=f"图片文件不存在: {req.image_path}")

    mgr = get_free_web_ai_manager()
    result = await mgr.ask_with_image(req.question, req.image_path, provider=req.provider)
    return WebAiResponse(
        success=result.get("success", False),
        response=result.get("response"),
        provider=result.get("provider"),
        reason=result.get("reason"),
        reasons=result.get("reasons"),
    )


@router.post("/smoke", response_model=list[dict[str, Any]])
async def free_web_ai_smoke(
    current_user: User = Depends(get_current_active_user),
) -> list[dict[str, Any]]:
    """测试所有 provider 可达性。"""
    _require_permission(current_user)
    mgr = get_free_web_ai_manager()
    return await mgr.smoke_test()


def _require_permission(user: User) -> None:
    """简单的权限检查 — 后续可改用 require_permission 装饰器。"""
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
