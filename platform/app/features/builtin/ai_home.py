"""AI 助理 — 企业级智能对话入口。"""

from __future__ import annotations

from app.api import ai_chat as ai_chat_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ai_home",
        title="AI 助理",
        description="多轮对话与办公场景智能问答，支持知识解读与引用溯源",
        icon="sparkles",
        route="/ai-home",
        router=ai_chat_api.router,
        permission_code="feature.ai_home",
        permission_name="AI 助理",
        enabled=True,
        category="ai",
        sort_order=1,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
