"""辅助写作 — Markdown 编辑 + AI 改写。"""

from __future__ import annotations

from app.api import assist_writing as assist_writing_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="assist_writing",
        title="辅助写作",
        description="Markdown 双栏编辑，预设提示词由 AI 润色、扩写与续写",
        icon="create",
        route="/system/assist-writing",
        router=assist_writing_api.router,
        permission_code="feature.assist_writing",
        permission_name="辅助写作",
        enabled=True,
        category="document",
        sort_order=15,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
