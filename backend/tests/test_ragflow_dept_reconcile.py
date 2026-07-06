"""角色种子：仅系统管理员与普通用户。"""

from unittest.mock import MagicMock, patch

from app.core.permissions import DEFAULT_ROLES, describe_user_tier


def test_default_roles_two_tiers():
    assert "sys_admin" in DEFAULT_ROLES
    assert DEFAULT_ROLES["sys_admin"]["name"] == "系统管理员"
    assert "member" in DEFAULT_ROLES
    assert DEFAULT_ROLES["member"]["name"] == "普通用户"
    assert "company_admin" not in DEFAULT_ROLES
    assert "dept_admin" not in DEFAULT_ROLES
    assert "doc.dept.create" in DEFAULT_ROLES["member"]["permissions"]
    assert "doc.company.create" in DEFAULT_ROLES["member"]["permissions"]


def test_describe_user_tier_member():
    db = MagicMock()
    user = MagicMock()
    with patch("app.core.permissions.user_is_system_admin", return_value=False):
        assert describe_user_tier(db, user) == "member"
