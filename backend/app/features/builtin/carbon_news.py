"""碳新闻 — 发改委政策/新闻实时爬取与一问一答。"""

from __future__ import annotations

from app.api import carbon_news as carbon_news_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_news",
        title="碳新闻",
        description="爬取双碳政策与新闻，基于当次内容一问一答并附数据来源",
        icon="newspaper",
        route="/system/carbon-news",
        router=carbon_news_api.router,
        permission_code="feature.carbon_news",
        permission_name="碳新闻",
        enabled=True,
        category="carbon",
        sort_order=47,
        grant_to_roles=("sys_admin", "member"),
    )
)
