"""根据当前版本文件名 / MIME 推断列表展示的文档格式标签。"""

from __future__ import annotations

_EXT_LABELS: dict[str, str] = {
    "pdf": "pdf",
    "doc": "word",
    "docx": "word",
    "dot": "word",
    "dotx": "word",
    "txt": "txt",
    "md": "md",
    "markdown": "md",
    "rtf": "rtf",
    "xls": "excel",
    "xlsx": "excel",
    "csv": "csv",
    "ppt": "ppt",
    "pptx": "ppt",
    "html": "html",
    "htm": "html",
    "json": "json",
    "xml": "xml",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "webp": "image",
    "zip": "zip",
    "rar": "rar",
    "7z": "archive",
}

_MIME_LABELS: dict[str, str] = {
    "application/pdf": "pdf",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/vnd.ms-excel": "excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
    "text/csv": "csv",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt",
}


def version_file_format_label(
    file_name: str | None, mime_type: str | None = None
) -> str | None:
    """返回小写格式标签（如 pdf、word、txt），无则 None。"""
    if file_name and "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower().strip()
        if ext in _EXT_LABELS:
            return _EXT_LABELS[ext]
    if mime_type:
        mt = mime_type.split(";")[0].strip().lower()
        if mt in _MIME_LABELS:
            return _MIME_LABELS[mt]
        if mt.startswith("image/"):
            return "image"
    if file_name and "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower().strip()
        if ext and ext.isalnum() and len(ext) <= 8:
            return ext
    return None
