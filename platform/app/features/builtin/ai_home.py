"""AI 智能体 — 企业级智能对话入口。"""

from __future__ import annotations

from app.api import ai_chat as ai_chat_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ai_home",
        title="本析智能",
        description="企业级智能对话入口；按需发现与调用 Agent Skills，结合权限内检索、本体关联与多轮问答",
        icon="sparkles",
        route="/ai-home",
        router=ai_chat_api.router,
        permission_code="feature.ai_home",
        permission_name="本析智能",
        enabled=True,
        category="ai",
        sort_order=1,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
