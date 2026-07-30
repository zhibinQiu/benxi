from __future__ import annotations

from app.api.carbon_assistant import router as carbon_assistant_router
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_assistant",
        title="碳资产报告",
        description="控排企业履约核算与碳交易策略推荐（火电/钢铁/水泥/电解铝）",
        icon="leaf",
        route="/system/carbon-assistant",
        router=carbon_assistant_router,
        permission_code="feature.carbon_assistant",
        permission_name="碳资产报告",
        enabled=True,
        category="carbon",
        sort_order=45,
        grant_to_roles=("sys_admin", "member"),
    )
)
