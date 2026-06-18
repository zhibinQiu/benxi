"""文本清洗：PostgreSQL 等数据库不接受 NUL 字符。"""

from __future__ import annotations


def sanitize_db_text(text: str | None) -> str:
    if not text:
        return ""
    return str(text).replace("\x00", "")
