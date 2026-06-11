"""统一资讯订阅（手动链接收录）。"""

from __future__ import annotations

from app.api import subscriptions as subscriptions_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="subscriptions",
        title="网站收藏",
        description="粘贴文章链接收录资讯，统一浏览并导入「个人级」文档库",
        icon="newspaper",
        route="/knowledge/subscriptions",
        router=subscriptions_api.router,
        permission_code="feature.subscriptions",
        permission_name="资讯订阅",
        enabled=True,
        tag="可用",
        category="tools",
        sort_order=34,
        show_in_catalog=False,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
