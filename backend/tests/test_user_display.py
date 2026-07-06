"""用户展示名解析。"""

from __future__ import annotations

import uuid

from app.core.user_display import user_display_name
from app.models.org import User


def test_user_display_name_prefers_display_name():
    user = User(
        id=uuid.uuid4(),
        display_name="张三",
        username="zhangsan",
        phone="13800000001",
        email="zhang@example.com",
        password_hash="x",
    )
    assert user_display_name(user) == "张三"


def test_user_display_name_falls_back_to_email():
    user = User(
        id=uuid.uuid4(),
        display_name="",
        username="",
        phone=None,
        email="only-email@example.com",
        password_hash="x",
    )
    assert user_display_name(user) == "only-email@example.com"


def test_user_display_name_missing_user():
    assert user_display_name(None) == "未知用户"
