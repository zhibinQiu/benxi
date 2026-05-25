from __future__ import annotations

from app.api import compare as compare_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="doc_compare",
        title="文档对比",
        description="左右对照比对 PDF/Word，差异高亮与自然语言检索",
        icon="git-compare",
        route="/system/compare",
        router=compare_api.router,
        permission_code="feature.doc_compare",
        permission_name="文档对比",
        enabled=True,
        category="document",
        sort_order=25,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
