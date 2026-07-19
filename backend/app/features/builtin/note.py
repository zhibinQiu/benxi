"""工作笔记 — FeaturePlugin 注册。"""

from __future__ import annotations

from app.api.note import router as note_router
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="notes",
        title="工作笔记",
        description="个人笔记管理，支持 Markdown 编辑、文件夹分类与图片粘贴",
        icon="journal",
        route="/system/notes",
        router=note_router,
        permission_code="feature.notes",
        permission_name="工作笔记",
        enabled=True,
        category="tools",
        sort_order=45,
        grant_to_roles=("sys_admin", "member"),
    )
)
