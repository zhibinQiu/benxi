"""智能问数 — 自然语言问数对话（Dify Chatflow）。"""

from __future__ import annotations

from app.api import smart_data_query_v2 as smart_data_query_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="smart_data_query",
        title="智能问数",
        description="用自然语言查询业务数据，自动生成统计图表与分析洞察",
        icon="stats-chart",
        route="/system/smart-data-query",
        router=smart_data_query_api.router,
        permission_code="feature.smart_data_query",
        permission_name="智能问数",
        enabled=True,
        category="carbon",
        sort_order=45,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
