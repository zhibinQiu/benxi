"""AIP 身份凭证（GB/Z 185.3）— SK 生成与校验。"""

from __future__ import annotations

import hashlib
import secrets

SK_PREFIX = "sk-aip-"
_KEY_BODY_BYTES = 24


def is_aip_sk_token(raw: str | None) -> bool:
    """是否为 AIP Secret Key 格式。"""
    return bool(raw) and str(raw).strip().startswith(SK_PREFIX)


def hash_aip_sk(raw: str) -> str:
    """SK 单向哈希（库内仅存摘要）。"""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def sk_display_prefix(raw: str) -> str:
    """列表展示用前缀（不含完整密钥）。"""
    clean = raw.strip()
    if len(clean) <= 16:
        return clean
    return f"{clean[:16]}…"


def generate_aip_sk() -> tuple[str, str, str]:
    """生成 SK，返回 (完整密钥, 展示前缀, 哈希)。"""
    body = secrets.token_urlsafe(_KEY_BODY_BYTES)
    full = f"{SK_PREFIX}{body}"
    return full, sk_display_prefix(full), hash_aip_sk(full)
