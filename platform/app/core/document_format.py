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


_FORMAT_DISPLAY: dict[str, str] = {
    "pdf": "PDF",
    "word": "Word",
    "txt": "TXT",
    "md": "Markdown",
    "excel": "Excel",
    "csv": "CSV",
    "ppt": "PPT",
    "html": "HTML",
    "image": "图片",
    "zip": "ZIP",
    "rar": "RAR",
    "archive": "压缩包",
}


def format_label_display(label: str | None) -> str:
    if not label:
        return "未知格式"
    key = label.lower().strip()
    return _FORMAT_DISPLAY.get(key, key.upper())


def assert_compatible_version_format(
    *,
    existing_file_name: str | None,
    existing_mime: str | None,
    new_file_name: str,
    new_mime: str,
) -> None:
    """新版本须与已有版本文件格式一致，否则抛出 bad_request。"""
    expected = version_file_format_label(existing_file_name, existing_mime)
    incoming = version_file_format_label(new_file_name, new_mime)
    if not expected or not incoming:
        ext_old = (
            existing_file_name.rsplit(".", 1)[-1].lower()
            if existing_file_name and "." in existing_file_name
            else None
        )
        ext_new = (
            new_file_name.rsplit(".", 1)[-1].lower()
            if new_file_name and "." in new_file_name
            else None
        )
        if ext_old and ext_new and ext_old != ext_new:
            from app.core.exceptions import bad_request

            raise bad_request(
                f"新版本文件扩展名须与已有版本一致（当前 .{ext_old}，上传 .{ext_new}）"
            )
        return
    if expected != incoming:
        from app.core.exceptions import bad_request

        raise bad_request(
            "新版本文件格式须与已有版本一致"
            f"（当前 {format_label_display(expected)}，上传 {format_label_display(incoming)}）"
        )
