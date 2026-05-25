"""OCR 识别：系统功能入口（界面已接入，后端待实现）。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ocr",
        title="OCR 识别",
        description="上传图像或文档，提取文字内容",
        icon="scan",
        route="/system/ocr",
        router=None,
        permission_code="feature.ocr",
        permission_name="OCR 识别",
        enabled=True,
        tag="界面预览",
        category="tools",
        sort_order=18,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
