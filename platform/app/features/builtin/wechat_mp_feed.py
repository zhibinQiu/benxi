"""公众号资讯 — 用户维护跟踪列表，汇总推文并支持入知识库。"""

from __future__ import annotations

from app.api import wechat_mp as wechat_mp_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="wechat_mp_feed",
        title="公众号资讯",
        description="跟踪关注的公众号，以卡片浏览推文并导入文档库检索",
        icon="newspaper",
        route="/knowledge/wechat-mp",
        router=wechat_mp_api.router,
        permission_code="feature.wechat_mp_feed",
        permission_name="公众号资讯",
        enabled=True,
        tag="可用",
        category="tools",
        sort_order=36,
        show_in_catalog=False,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
