"""本体图谱 — 本体驱动的实体关系调查工作台。"""

from __future__ import annotations

from app.api import kg as kg_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="kg_palantir",
        title="本体图谱",
        description="查询、编辑实体关系网络；本体类型配置与文档自动抽取",
        icon="git-network",
        route="/system/kg-palantir",
        router=kg_api.router,
        permission_code="feature.kg_palantir",
        permission_name="本体图谱",
        enabled=True,
        category="tools",
        sort_order=22,
        grant_to_roles=("sys_admin", "member"),
    )
)
