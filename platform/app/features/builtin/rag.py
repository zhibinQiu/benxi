from __future__ import annotations

from app.api import rag as rag_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="rag_qa",
        title="编码管理",
        description="KnowFlow 知识库编码与问答配置，支持引用溯源与文档定位",
        icon="chatbubbles",
        route="/system/rag",
        router=rag_api.router,
        permission_code="feature.rag_qa",
        permission_name="编码管理",
        enabled=True,
        category="document",
        sort_order=20,
        show_in_catalog=False,
        grant_to_roles=("sys_admin",),
    )
)
