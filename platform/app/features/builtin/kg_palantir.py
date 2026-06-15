"""Palantir 与知识图谱 — 本体驱动的实体关系调查工作台。"""

from __future__ import annotations

from app.api import kg as kg_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="kg_palantir",
        title="Palantir与知识图谱",
        description="本体建模、实体关系编辑与关联探索；从文档与资讯抽取结构化知识网络",
        icon="git-network",
        route="/system/kg-palantir",
        router=kg_api.router,
        permission_code="feature.kg_palantir",
        permission_name="Palantir与知识图谱",
        enabled=True,
        category="tools",
        sort_order=22,
        grant_to_roles=("sys_admin", "member"),
    )
)
