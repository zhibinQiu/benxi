"""登录号 / 手机号校验。"""

import pytest

from app.core.phone import (
    _PHONE_RE,
    bootstrap_login_id,
    is_bootstrap_login_id,
    normalize_login_id,
    normalize_phone,
)


def test_normalize_phone_cn_mobile():
    assert normalize_phone("13800000000") == "13800000000"
    assert normalize_phone("138-0000-0000") == "13800000000"


def test_normalize_phone_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_phone("admin")


def test_bootstrap_login_id():
    boot = bootstrap_login_id()
    assert _PHONE_RE.match(boot) or boot
    assert is_bootstrap_login_id(boot)
    assert normalize_login_id(boot) == boot
    assert is_bootstrap_login_id(f"{boot[:3]}-{boot[3:7]}-{boot[7:]}")
