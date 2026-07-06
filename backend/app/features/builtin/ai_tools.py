"""在线 AI 工具：系统功能入口，外链由前端页面承载。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ai_tools",
        title="在线 AI 工具",
        description="对话、Agent、生图视频及其他 AI 外链合集（需联网）",
        icon="sparkles",
        route="/system/ai-tools",
        permission_code="feature.ai_tools",
        permission_name="在线 AI 工具",
        enabled=True,
        tag="需联网",
        category="tools",
        sort_order=35,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
