from __future__ import annotations

from app.api.finance import router as finance_router
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="finance_assistant",
        title="理财助手",
        description="AI 解读、多角色圆桌辩论与量价会诊，生成可复核的股票研究报告",
        icon="trending-up",
        route="/system/finance",
        router=finance_router,
        permission_code="feature.finance_assistant",
        permission_name="理财助手",
        enabled=True,
        category="tools",
        sort_order=50,
        grant_to_roles=("sys_admin", "member"),
    )
)
