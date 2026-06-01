"""KnowFlow 平台一体化 — 阶段 1 单元测试。"""

from __future__ import annotations

import uuid

from app.models.org import User
from app.services.ragflow_naming import (
    dataset_name_for_dept,
    dataset_name_for_user,
    platform_email_for_user,
)


def test_dataset_name_per_user():
    u1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    u2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    assert dataset_name_for_user(u1) != dataset_name_for_user(u2)
    assert dataset_name_for_user(u1).startswith("zt-personal-")


def test_dataset_name_for_dept_prefix():
    did = uuid.UUID("33333333-3333-3333-3333-333333333333")
    assert dataset_name_for_dept(did).startswith("zt-dept-")


def test_platform_email():
    from unittest.mock import MagicMock, patch

    mapped = MagicMock(ragflow_account_mode="mapped", ragflow_shared_email="")
    user = User(
        username="alice",
        email="alice@corp.com",
        password_hash="x",
        display_name="Alice",
    )
    with patch("app.services.ragflow_naming.get_settings", return_value=mapped):
        assert platform_email_for_user(user).endswith("@platform.local")
        assert platform_email_for_user(user).startswith("alice-")
        user2 = User(username="bob", email=None, password_hash="x", display_name="Bob")
        assert platform_email_for_user(user2).startswith("bob-")
        admin = User(
            id=uuid.UUID("caf46c9d-0000-0000-0000-000000000001"),
            username="admin",
            email="admin@local",
            password_hash="x",
            display_name="Admin",
        )
        assert platform_email_for_user(admin) == "admin-caf46c9d@platform.local"

    shared_settings = MagicMock(
        ragflow_account_mode="shared",
        ragflow_shared_email="admin@gmail.com",
    )
    with patch("app.services.ragflow_naming.get_settings", return_value=shared_settings):
        admin = User(
            username="admin",
            email="admin@local",
            password_hash="x",
            display_name="Admin",
        )
        assert platform_email_for_user(admin) == "admin@gmail.com"
