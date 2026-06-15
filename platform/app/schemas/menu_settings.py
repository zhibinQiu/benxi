"""侧栏菜单可见性配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MenuItemOut(BaseModel):
    key: str
    label: str
    group: str = "main"
    description: str = ""


class MenuSettingsOut(BaseModel):
    items: list[MenuItemOut]
    member_visible: dict[str, bool]


class MenuSettingsUpdate(BaseModel):
    member_visible: dict[str, bool] = Field(default_factory=dict)


class VisibleMenusOut(BaseModel):
    keys: list[str]
