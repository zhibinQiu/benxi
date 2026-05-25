from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="smart_forecast",
        title="智能预测",
        description="能耗与碳排趋势预测及情景分析",
        icon="stats-chart",
        route="/system/smart-forecast",
        embed_url=None,
        permission_code="feature.smart_forecast",
        permission_name="智能预测",
        enabled=True,
        category="carbon",
        sort_order=48,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
