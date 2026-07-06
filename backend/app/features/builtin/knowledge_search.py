from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="knowledge_search",
        title="知识检索",
        description="在企业知识库中检索文档与片段，支持引用溯源",
        icon="search",
        route="/knowledge/search",
        permission_code="feature.knowledge_search",
        permission_name="知识检索",
        enabled=True,
        category="document",
        sort_order=25,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
