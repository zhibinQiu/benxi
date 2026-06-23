"""文本清洗：PostgreSQL / JSONB 不接受 NUL 与孤立 UTF-16 代理对。"""

from __future__ import annotations


def sanitize_db_text(text: str | None) -> str:
    if not text:
        return ""
    return str(text).replace("\x00", "")


def sanitize_json_text(text: str | None) -> str:
    """移除 NUL 与无效代理对，避免 JSONB 写入失败。"""
    cleaned = sanitize_db_text(text)
    if not cleaned:
        return ""
    return cleaned.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
