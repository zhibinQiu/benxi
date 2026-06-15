"""PageIndex 实验性检索 — 无向量库、基于树结构的推理检索 Demo。"""

from __future__ import annotations

from app.api import pageindex as pageindex_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="pageindex_demo",
        title="PageIndex 检索",
        description="实验性：基于 PageIndex 树形索引的推理检索（无向量分块），用于对比传统 RAG 效果",
        icon="git-branch",
        route="/system/pageindex",
        router=pageindex_api.router,
        permission_code="feature.pageindex_demo",
        permission_name="PageIndex 检索",
        enabled=False,
        tag="已并入知识检索",
        category="document",
        sort_order=26,
        grant_to_roles=("sys_admin", "member"),
    )
)
