"""占位功能：仅出现在系统功能清单，待实现后改为独立插件模块并挂载 router。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

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
        category="document",
        sort_order=30,
        grant_to_roles=("sys_admin", "member"),
    )
)
