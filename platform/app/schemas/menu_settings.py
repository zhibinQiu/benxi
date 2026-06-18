"""侧栏菜单可见性配置。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MenuVisibility = Literal["all", "admin", "hidden"]


class MenuItemOut(BaseModel):
    key: str
    label: str
    group: str = "main"
    description: str = ""


class MenuSettingsOut(BaseModel):
    items: list[MenuItemOut]
    menu_visibility: dict[str, MenuVisibility]


class MenuSettingsUpdate(BaseModel):
    menu_visibility: dict[str, MenuVisibility] = Field(default_factory=dict)
    member_visible: dict[str, bool] | None = None


class VisibleMenusOut(BaseModel):
    keys: list[str]
