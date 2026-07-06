"""通用文本处理。"""

from __future__ import annotations


def truncate_text(text: str, limit: int, *, suffix: str = "\n…（后文已截断）") -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    trim = max(1, len(suffix))
    return t[: limit - trim] + suffix
