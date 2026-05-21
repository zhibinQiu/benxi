from __future__ import annotations

from app.api import translate as translate_api
from app.features.base import FeaturePlugin
from app.features.registry import register

translate_plugin = FeaturePlugin(
    id="pdf_translate",
    title="PDF 翻译",
    description="保留版式的高质量 PDF 翻译，支持术语表与多引擎",
    icon="language",
    route="/system/translate",
    router=translate_api.router,
    permission_code="feature.translate",
    permission_name="PDF 翻译",
    enabled=True,
    sort_order=10,
    grant_to_roles=("sys_admin", "dept_admin", "member"),
)

register(translate_plugin)
