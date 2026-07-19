from __future__ import annotations

from app.api.prompt import router as prompt_router
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="prompt_management",
        title="提示词管理",
        description="保存、管理和快速复制常用 AI 提示词模板",
        icon="clipboard-outline",
        route="/system/prompts",
        router=prompt_router,
        permission_code="feature.prompt_management",
        permission_name="提示词管理",
        enabled=True,
        category="tools",
        sort_order=55,
        grant_to_roles=("sys_admin", "member"),
    )
)
