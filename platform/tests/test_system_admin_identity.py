"""系统管理员身份：内置 admin 与 sys_admin 角色。"""

import uuid
from unittest.mock import MagicMock, patch

from app.core.permissions import user_is_system_admin, user_is_superuser


def test_sys_admin_role_is_system_admin():
    user = MagicMock(id=uuid.uuid4(), phone="13800000001")
    db = MagicMock()
    with patch(
        "app.core.platform_admin.user_has_system_admin_role", return_value=True
    ):
        assert user_is_system_admin(db, user)
        assert user_is_superuser(db, user)


def test_member_without_sys_admin_role_is_not_system_admin():
    user = MagicMock(id=uuid.uuid4(), phone="13800000001")
    db = MagicMock()
    with patch(
        "app.core.platform_admin.user_has_system_admin_role", return_value=False
    ):
        assert not user_is_system_admin(db, user)


def test_member_is_not_system_admin():
    user = MagicMock(id=uuid.uuid4(), phone="13800000002")
    db = MagicMock()
    with patch(
        "app.core.platform_admin.user_has_system_admin_role", return_value=False
    ):
        assert not user_is_system_admin(db, user)
