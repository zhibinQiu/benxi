"""RSS / 网站资讯订阅。"""

from __future__ import annotations

from app.api import feed_subscriptions as feed_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="feed_subscriptions",
        title="RSS 与网站订阅",
        description="订阅双碳相关网站 RSS/Atom 源，汇总资讯并导入文档库",
        icon="stats-chart",
        route="/knowledge/feed-subscriptions",
        router=feed_api.router,
        permission_code="feature.feed_subscriptions",
        permission_name="RSS 与网站订阅",
        enabled=False,
        tag="已合并",
        category="tools",
        sort_order=35,
        show_in_catalog=False,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
