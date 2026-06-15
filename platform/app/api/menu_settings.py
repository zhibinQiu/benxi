"""侧栏菜单可见性 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.menu_settings import MenuSettingsOut, MenuSettingsUpdate, VisibleMenusOut
from app.services.menu_settings_service import (
    get_menu_settings,
    resolve_visible_menu_keys,
    save_menu_settings,
)

router = APIRouter(tags=["menu-settings"])


@router.get("/system/menus", response_model=ApiResponse[VisibleMenusOut])
def read_visible_menus(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[VisibleMenusOut]:
    """当前用户侧栏可见菜单项。"""
    return ApiResponse(data=resolve_visible_menu_keys(db, user))


@router.get("/admin/menu-settings", response_model=ApiResponse[MenuSettingsOut])
def read_menu_settings_admin(
    _: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MenuSettingsOut]:
    return ApiResponse(data=get_menu_settings(db))


@router.put("/admin/menu-settings", response_model=ApiResponse[MenuSettingsOut])
def update_menu_settings_admin(
    body: MenuSettingsUpdate,
    _: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MenuSettingsOut]:
    return ApiResponse(data=save_menu_settings(db, body.member_visible))
