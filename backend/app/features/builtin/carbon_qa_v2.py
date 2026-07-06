"""双碳问答 — 自然语言问答对话（Dify Chatflow）。"""

from __future__ import annotations

from app.api import carbon_qa_v2 as carbon_qa_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_qa",
        title="双碳问答",
        description="双碳政策、标准与业务知识智能问答，支持多轮深度解读",
        icon="chatbubbles",
        route="/system/carbon-qa",
        router=carbon_qa_api.router,
        permission_code="feature.carbon_qa",
        permission_name="双碳问答",
        enabled=True,
        category="carbon",
        sort_order=46,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
