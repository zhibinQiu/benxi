"""System feature catalog (hub page) — driven by feature plugins."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import not_found
from app.core.permissions import user_has_permission
from app.database import get_db
from app.features.registry import all_plugins, ensure_plugins_loaded, get_plugin
from app.models.org import User
from app.config import get_settings
from app.schemas.common import ApiResponse
from app import __version__

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


@router.get("/features")
async def list_features(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[dict]]:
    """功能清单：由插件注册表生成，按用户权限过滤可进入的路由。"""
    ensure_plugins_loaded()
    items = []
    for plugin in all_plugins():
        if not getattr(plugin, "show_in_catalog", True):
            continue
        if not plugin.enabled:
            items.append(plugin.catalog_dict(accessible=False))
            continue
        allowed = user_has_permission(db, user, plugin.permission_code)
        items.append(plugin.catalog_dict(accessible=allowed))
    return ApiResponse(data=items)


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
