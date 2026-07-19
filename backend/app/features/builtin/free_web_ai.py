"""免费网页 AI FeaturePlugin 注册。"""

from __future__ import annotations

from app.api import free_web_ai as free_web_ai_api
from app.features.base import FeaturePlugin
from app.features.registry import register

free_web_ai_plugin = FeaturePlugin(
    id="free_web_ai",
    title="免费网页 AI",
    description="通过浏览器桥接豆包/千问/DeepSeek 等免费 Web AI，支持对话、生图、识图",
    icon="globe",
    route="/system/free-web-ai",
    router=free_web_ai_api.router,
    permission_code="feature.free_web_ai",
    permission_name="免费网页 AI",
    enabled=True,
    category="ai",
    sort_order=60,
    show_in_catalog=False,
    grant_to_roles=("sys_admin", "member"),
)

register(free_web_ai_plugin)
