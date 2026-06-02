"""碳资产管理与交易 — demo。"""

from __future__ import annotations

from app.api import carbon_asset as carbon_asset_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_asset_trading",
        title="碳资产管理与交易",
        description="碳配额/CCER 持仓、环交所 CEA 行情与模拟交易",
        icon="wallet",
        route="/system/carbon-assets",
        router=carbon_asset_api.router,
        permission_code="feature.carbon_asset_trading",
        permission_name="碳资产管理与交易",
        enabled=True,
        tag="Demo",
        category="carbon",
        sort_order=47,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
