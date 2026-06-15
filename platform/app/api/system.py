"""System feature catalog (hub page) — driven by feature plugins."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_current_user
from app.config import get_settings
from app.core.exceptions import not_found
from app.core.permissions import user_has_permission
from app.database import get_db
from app.features.registry import all_plugins, ensure_plugins_loaded, get_plugin
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.dashboard import PlatformDashboardStatsOut
from app.schemas.model_settings import ClientConfigOut
from app.services.model_settings_service import (
    get_frontend_app_title,
    get_frontend_default_theme,
    get_platform_api_base_url,
)
from app.services.platform_dashboard_service import collect_platform_dashboard_stats

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/version")
def system_version() -> ApiResponse[dict]:
    """平台版本信息（无需登录，供前端与运维核对）。"""
    settings = get_settings()
    ver = (settings.platform_version or __version__).strip()
    label = ver.split(".", 1)[0]
    if label.isdigit():
        label = f"v{label}"
    return ApiResponse(
        data={
            "version": ver,
            "version_label": label,
            "app_name": settings.app_name,
        }
    )


@router.get("/client-config", response_model=ApiResponse[ClientConfigOut])
def client_config(db: Annotated[Session, Depends(get_db)]) -> ApiResponse[ClientConfigOut]:
    """前端启动配置（无需登录）：浏览器请求平台后端的根地址与前台展示项。"""
    return ApiResponse(
        data=ClientConfigOut(
            api_base=get_platform_api_base_url(db),
            app_title=get_frontend_app_title(db),
            default_theme=get_frontend_default_theme(db),
        )
    )


@router.get("/features")
async def list_features(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[dict]]:
    """功能清单：由插件注册表生成，按用户权限过滤可进入的路由。"""
    ensure_plugins_loaded()
    catalog_plugins = [
        p for p in all_plugins() if getattr(p, "show_in_catalog", True)
    ]
    # 已上线功能在前，待开发（enabled=False）在后；组内仍按 sort_order。
    ordered_plugins = [
        p for p in catalog_plugins if p.enabled
    ] + [p for p in catalog_plugins if not p.enabled]
    items = []
    for plugin in ordered_plugins:
        if not plugin.enabled:
            items.append(plugin.catalog_dict(accessible=False))
            continue
        allowed = user_has_permission(db, user, plugin.permission_code)
        items.append(plugin.catalog_dict(accessible=allowed))
    return ApiResponse(data=items)


@router.get("/dashboard-stats", response_model=ApiResponse[PlatformDashboardStatsOut])
def get_dashboard_stats(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[PlatformDashboardStatsOut]:
    """运行大屏：平台级文档、功能与用户统计。"""
    return ApiResponse(
        data=PlatformDashboardStatsOut.model_validate(collect_platform_dashboard_stats(db))
    )


def _resolve_embed_url(feature_id: str) -> str:
    from app.services.feature_embed_urls import resolve_feature_embed_url

    url = resolve_feature_embed_url(feature_id)
    if url:
        return url
    plugin = get_plugin(feature_id)
    if not plugin:
        return ""
    return (plugin.embed_url or "").strip()


@router.get("/features/{feature_id}/embed-meta")
async def feature_embed_meta(
    feature_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """内嵌页元数据（智能预测等 iframe 功能）。"""
    ensure_plugins_loaded()
    plugin = get_plugin(feature_id)
    if not plugin or not plugin.enabled:
        raise not_found("Feature not found")
    if not user_has_permission(db, user, plugin.permission_code):
        from app.core.exceptions import forbidden

        raise forbidden(f"Missing permission: {plugin.permission_code}")
    url = _resolve_embed_url(feature_id)
    requires_auth = feature_id != "smart_forecast"
    return ApiResponse(
        data={
            "embed_url": url,
            "available": bool(url),
            "requires_auth": requires_auth,
        }
    )
