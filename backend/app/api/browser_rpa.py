"""浏览器 RPA 截图代理与状态 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.integrations.browser_automation.browser_config import get_browser_rpa_config
from app.models.org import User
from app.schemas.common import ApiResponse
from app.services.browser_rpa_service import fetch_screenshot_bytes

router = APIRouter(prefix="/browser-rpa", tags=["browser-rpa"])


@router.get("/screenshot")
def browser_screenshot_proxy(
    key: str = Query(..., min_length=8),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """代理 MinIO 中的 RPA 截图（避免浏览器无法访问内网 presigned URL）。"""
    _ = user
    cfg = get_browser_rpa_config(db)
    if not cfg.enabled:
        return Response(status_code=404)
    data = fetch_screenshot_bytes(key.strip())
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/png")


@router.get("/status", response_model=ApiResponse[dict])
def browser_rpa_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
    _ = user
    cfg = get_browser_rpa_config(db)
    return ApiResponse(
        data={
            "enabled": cfg.enabled,
            "headless": cfg.headless,
            "allowed_domains": cfg.allowed_domains,
            "auto_task_enabled": cfg.auto_task_enabled,
            "note": (
                "无头服务器部署：Chromium 以 headless 模式运行，无需显示器或 X11。"
                if cfg.headless
                else "非 headless 模式需图形环境，不建议在生产无头服务器使用。"
            ),
        }
    )
