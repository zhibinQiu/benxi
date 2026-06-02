"""登录标识：普通用户与唯一系统管理员均为 11 位手机号（管理员号见 bootstrap_admin_phone）。"""

from __future__ import annotations

import re

from app.config import get_settings

_PHONE_RE = re.compile(r"^1\d{10}$")


def bootstrap_login_id() -> str:
    """唯一系统管理员登录手机号（存于 users.phone）。"""
    raw = (get_settings().bootstrap_admin_phone or "").strip()
    if _PHONE_RE.match(raw):
        return raw
    return raw or "15963564658"


def is_bootstrap_login_id(value: str) -> bool:
    boot = bootstrap_login_id()
    raw = (value or "").strip()
    if not raw:
        return False
    if _PHONE_RE.match(boot):
        try:
            return normalize_phone(raw) == boot
        except ValueError:
            return False
    return raw.lower() == boot.lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", (value or "").strip())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not _PHONE_RE.match(digits):
        raise ValueError("请输入有效的 11 位手机号")
    return digits


def normalize_login_id(value: str) -> str:
    """登录/注册入参：超级管理员 ID 或手机号。"""
    if is_bootstrap_login_id(value):
        return bootstrap_login_id()
    return normalize_phone(value)


def login_ids_equal(a: str, b: str) -> bool:
    if is_bootstrap_login_id(a) or is_bootstrap_login_id(b):
        return is_bootstrap_login_id(a) and is_bootstrap_login_id(b)
    try:
        return normalize_phone(a) == normalize_phone(b)
    except ValueError:
        return False
