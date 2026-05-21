"""占位功能：仅出现在系统功能清单，待实现后改为独立插件模块并挂载 router。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="rag_qa",
        title="知识问答",
        description="基于企业知识库的 RAG 问答（对接 KnowFlow，筹备中）",
        icon="chatbubbles",
        permission_code="feature.rag_qa",
        permission_name="知识问答",
        enabled=False,
        tag="即将推出",
        sort_order=20,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)

register(
    FeaturePlugin(
        id="doc_compare",
        title="文档对比",
        description="多版本文档差异对比",
        icon="git-compare",
        permission_code="feature.doc_compare",
        permission_name="文档对比",
        enabled=False,
        tag="即将推出",
        sort_order=30,
        grant_to_roles=("sys_admin", "dept_admin"),
    )
)

register(
    FeaturePlugin(
        id="doc_generate",
        title="文档生成",
        description="模板化自动文档生成",
        icon="document-text",
        permission_code="feature.doc_generate",
        permission_name="文档生成",
        enabled=False,
        tag="即将推出",
        sort_order=40,
        grant_to_roles=("sys_admin", "dept_admin"),
    )
)
