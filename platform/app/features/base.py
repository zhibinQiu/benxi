"""Feature plugin contract — 新能力按插件接入平台。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter


@dataclass(frozen=True, slots=True)
class FeaturePlugin:
    """平台功能插件描述。

    新增功能时实现一个 ``FeaturePlugin`` 实例并 ``register()`` 即可：
    - 自动出现在「系统功能」清单（按权限过滤）
    - 权限码写入种子数据，可在角色管理中分配
    - ``router`` 非空时自动挂载到 ``/api/v1`` 下
    """

    id: str
    title: str
    description: str
    icon: str
    permission_code: str
    permission_name: str
    route: str | None = None
    router: APIRouter | None = None
    enabled: bool = True
    tag: str = "可用"
    sort_order: int = 100
    grant_to_roles: tuple[str, ...] = ("sys_admin", "dept_admin", "member")

    def catalog_dict(self, *, accessible: bool) -> dict[str, Any]:
        """供系统功能页展示的条目。"""
        if not self.enabled:
            return {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "icon": self.icon,
                "route": None,
                "enabled": False,
                "accessible": False,
                "tag": self.tag,
                "permission": self.permission_code,
            }
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "route": self.route if accessible else None,
            "enabled": True,
            "accessible": accessible,
            "tag": "可用" if accessible else "无权限",
            "permission": self.permission_code,
        }
