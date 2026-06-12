"""文件内容提取：调用平台 PaddleOCR-VL / layout-parsing 服务。"""

from __future__ import annotations

from app.api import ocr as ocr_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ocr",
        title="文件内容提取",
        description="上传图像或文档，提取文件文字内容",
        icon="scan",
        route="/system/ocr",
        router=ocr_api.router,
        permission_code="feature.ocr",
        permission_name="文件内容提取",
        enabled=True,
        category="tools",
        sort_order=18,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
