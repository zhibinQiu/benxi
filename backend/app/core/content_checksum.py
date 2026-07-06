"""文档二进制内容校验（MD5）。"""

from __future__ import annotations

import hashlib
import re

_MD5_HEX = re.compile(r"^[a-f0-9]{32}$", re.I)


def compute_md5_hex(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def normalize_checksum(value: str | None) -> str | None:
    """统一为 32 位小写 MD5 hex；无法识别时原样 strip。"""
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("md5:"):
        raw = raw[4:].strip()
    if _MD5_HEX.match(raw):
        return raw
    return raw
