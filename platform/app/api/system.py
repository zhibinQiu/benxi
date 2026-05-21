"""System feature catalog (hub page) — driven by feature plugins."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.permissions import user_has_permission
from app.database import get_db
from app.features.registry import all_plugins, ensure_plugins_loaded
from app.models.org import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/features")
async def list_features(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[dict]]:
    """功能清单：由插件注册表生成，按用户权限过滤可进入的路由。"""
    ensure_plugins_loaded()
    items = []
    for plugin in all_plugins():
        if not plugin.enabled:
            items.append(plugin.catalog_dict(accessible=False))
            continue
        allowed = user_has_permission(db, user, plugin.permission_code)
        items.append(plugin.catalog_dict(accessible=allowed))
    return ApiResponse(data=items)
