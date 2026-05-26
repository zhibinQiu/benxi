"""AI 首页 — 双碳智能体对话。"""

from __future__ import annotations

from app.api import ai_chat as ai_chat_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ai_home",
        title="双碳智能体",
        description="双碳领域专业对话，支持多轮问答与政策、核算、减排路径解读",
        icon="sparkles",
        route="/ai-home",
        router=ai_chat_api.router,
        permission_code="feature.ai_home",
        permission_name="双碳智能体",
        enabled=True,
        category="ai",
        sort_order=1,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
