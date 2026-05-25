from __future__ import annotations

from app.api import rag as rag_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="rag_qa",
        title="知识问答",
        description="基于企业知识库问答，支持引用溯源与文档定位",
        icon="chatbubbles",
        route="/system/rag",
        router=rag_api.router,
        permission_code="feature.rag_qa",
        permission_name="知识问答",
        enabled=True,
        category="document",
        sort_order=20,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
