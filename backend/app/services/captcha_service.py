"""滑块验证码服务 — 为 vue3-slide-verify 前端组件提供后端签牌验证。"""

from __future__ import annotations

import secrets
import time

# 已验证通过的 token 缓存（短期有效，防止重放）
_VERIFIED: dict[str, float] = {}

VERIFIED_TTL_SEC = 120  # 验证通过后 token 有效时间


def issue_token() -> str:
    """前端拼图验证通过后，颁发一个短期有效的验证 token。"""
    token = secrets.token_hex(16)
    _VERIFIED[token] = time.time()
    return token


def consume_verified(token: str) -> bool:
    """消耗一个已验证的 token（登录/注册时调用）。"""
    ts = _VERIFIED.pop(token, None)
    if ts is None:
        return False
    if time.time() - ts > VERIFIED_TTL_SEC:
        return False
    return True


def cleanup_expired() -> None:
    """清理过期的验证记录。"""
    now = time.time()
    for token, ts in list(_VERIFIED.items()):
        if now - ts > VERIFIED_TTL_SEC:
            del _VERIFIED[token]
