"""部门成员变动与 KnowFlow 部门库授权范围。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.permissions import DEFAULT_ROLES, describe_user_tier


def test_default_roles_include_four_tiers():
    assert "sys_admin" in DEFAULT_ROLES
    assert DEFAULT_ROLES["sys_admin"]["name"] == "系统管理员"
    assert "company_admin" in DEFAULT_ROLES
    assert DEFAULT_ROLES["company_admin"]["name"] == "公司级管理员"
    assert "dept_admin" in DEFAULT_ROLES
    assert "member" in DEFAULT_ROLES


def test_describe_user_tier():
    db = MagicMock()
    user = MagicMock(username="bob", id=uuid.uuid4())
    with patch("app.core.permissions.user_is_superuser", return_value=False), patch(
        "app.core.permissions.user_role_codes", return_value={"dept_admin"}
    ):
        assert describe_user_tier(db, user) == "dept_admin"


def test_revoke_stale_skips_current_departments():
    from app.services.ragflow_scope_service import revoke_stale_dept_kb_grants

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    dept_keep = uuid.uuid4()
    dept_leave = uuid.uuid4()

    reg_stay = MagicMock(scope="department", scope_key=str(dept_keep), ragflow_dataset_id="kb1")
    reg_go = MagicMock(scope="department", scope_key=str(dept_leave), ragflow_dataset_id="kb2")

    link = MagicMock(ragflow_user_id="rf-user-1")
    with patch(
        "app.services.ragflow_scope_service.get_or_create_link", return_value=link
    ), patch(
        "app.services.ragflow_scope_service.user_dept_ids", return_value=[dept_keep]
    ), patch(
        "app.services.ragflow_scope_service.select"
    ) as mock_select:
        mock_select.return_value.where.return_value = db.scalars.return_value
        db.scalars.return_value.all.return_value = [reg_stay, reg_go]
        with patch(
            "app.services.ragflow_scope_service.revoke_kb_user_permission",
            return_value=True,
        ) as revoke:
            n = revoke_stale_dept_kb_grants(db, user)
    assert n == 1
    revoke.assert_called_once_with("kb2", "rf-user-1")
