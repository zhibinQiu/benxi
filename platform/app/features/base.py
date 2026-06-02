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
    category: str = "tools"
    external_url: str | None = None
    embed_url: str | None = None
    grant_to_roles: tuple[str, ...] = ("sys_admin", "member")
    # False：不在「系统功能」页展示（改由知识中心 → 订阅 等入口进入）
    show_in_catalog: bool = True

    def _catalog_tag(self, *, accessible: bool) -> str:
        if not self.enabled:
            return self.tag
        if not accessible:
            return "无权限"
        if self.tag != "可用":
            return self.tag
        return "可用"

    def catalog_dict(self, *, accessible: bool) -> dict[str, Any]:
        """供系统功能页展示的条目。"""
        if not self.enabled:
            return {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "icon": self.icon,
                "category": self.category,
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
            "category": self.category,
            "route": self.route if accessible else None,
            "external_url": self.external_url if accessible and self.external_url else None,
            "embed_url": self.embed_url if accessible and self.embed_url else None,
            "enabled": True,
            "accessible": accessible,
            "tag": self._catalog_tag(accessible=accessible),
            "permission": self.permission_code,
        }
