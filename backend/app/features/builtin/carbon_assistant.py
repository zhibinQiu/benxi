from __future__ import annotations

from app.api.carbon_assistant import router as carbon_assistant_router
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_assistant",
        title="双碳助手",
        description="碳交易行情、碳报告与减碳策略，基于官方源数据与 AI 综合研判",
        icon="leaf",
        route="/system/carbon-assistant",
        router=carbon_assistant_router,
        permission_code="feature.carbon_assistant",
        permission_name="双碳助手",
        enabled=True,
        category="carbon",
        sort_order=45,
        grant_to_roles=("sys_admin", "member"),
    )
)
