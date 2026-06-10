"""文档中心单文件上传大小限制（与前端 documentUpload.js 保持一致）。"""

from __future__ import annotations

from app.config import get_settings


def document_upload_max_bytes() -> int:
    return get_settings().document_upload_max_file_mb * 1024 * 1024


def document_upload_max_label() -> str:
    mb = get_settings().document_upload_max_file_mb
    if mb >= 1024 and mb % 1024 == 0:
        return f"{mb // 1024}GB"
    return f"{mb}MB"
