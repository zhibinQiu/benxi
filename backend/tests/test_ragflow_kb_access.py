"""KnowFlow 知识库可见范围：个人 + 上级部门，不含他人库。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.ragflow_scope_dataset import SCOPE_PERSONAL as REG_PERSONAL
from app.services.ragflow_scope_service import (
    _dept_ids_for_kb_access,
    _should_grant_ragflow_global_admin,
    allowed_dataset_ids_for_user,
    revoke_unauthorized_kb_grants,
)


def test_dept_ids_for_kb_access_walks_ancestors_only():
    root = uuid.uuid4()
    dept = uuid.uuid4()
    team = uuid.uuid4()
    sibling = uuid.uuid4()
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())

    root_dept = MagicMock(id=root, parent_id=None)
    mid_dept = MagicMock(id=dept, parent_id=root)
    leaf_dept = MagicMock(id=team, parent_id=dept)
    db.get.side_effect = lambda _cls, pk: {
        team: leaf_dept,
        dept: mid_dept,
        root: root_dept,
    }.get(pk)

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service.user_department_id",
        return_value=team,
    ):
        ids = _dept_ids_for_kb_access(db, user)

    assert ids == [team, dept, root]
    assert sibling not in ids


def test_superuser_allowed_dataset_ids_include_all_registered():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    reg_a = MagicMock(ragflow_dataset_id="ds-a")
    reg_b = MagicMock(ragflow_dataset_id="ds-b")
    reg_empty = MagicMock(ragflow_dataset_id="")
    db.scalars.return_value.all.return_value = [reg_a, reg_b, reg_empty]

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=True,
    ):
        allowed = allowed_dataset_ids_for_user(db, user)

    assert allowed == {"ds-a", "ds-b"}


def test_revoke_ragflow_global_admin_uses_role_path():
    from app.integrations.ragflow_rbac import revoke_ragflow_global_admin

    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    check_resp = MagicMock(status_code=200)
    check_resp.json.return_value = {"has_permission": True}
    delete_resp = MagicMock(status_code=200)
    client.post.return_value = check_resp
    client.delete.return_value = delete_resp

    with patch("app.integrations.ragflow_rbac.httpx.Client", return_value=client), patch(
        "app.integrations.ragflow_rbac._has_global_admin",
        side_effect=[True, False],
    ):
        assert revoke_ragflow_global_admin("rag-user") is True

    client.delete.assert_called_once_with(
        "http://127.0.0.1:5001/api/v1/rbac/users/rag-user/roles/admin",
        params={"tenant_id": "default"},
    )


def test_mapped_user_gets_tenant_admin_for_personal_kb():
    db = MagicMock()
    user = MagicMock()
    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch("app.services.ragflow_scope_service.get_settings") as gs:
        gs.return_value.ragflow_grant_global_admin = False
        gs.return_value.ragflow_account_mode = "mapped"
        assert _should_grant_ragflow_global_admin(db, user) is True


def test_regular_user_should_not_get_global_admin_in_shared_without_flag():
    db = MagicMock()
    user = MagicMock()
    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch("app.services.ragflow_scope_service.get_settings") as gs:
        gs.return_value.ragflow_grant_global_admin = False
        gs.return_value.ragflow_account_mode = "shared"
        assert _should_grant_ragflow_global_admin(db, user) is False


def test_allowed_dataset_ids_without_personal_kb_only_dept_chain():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    dept_id = uuid.uuid4()
    dept_reg = MagicMock(ragflow_dataset_id="ds-dept", scope="department", scope_key=str(dept_id))
    company_reg = MagicMock(ragflow_dataset_id="ds-company", scope="company", scope_key="global")

    def _get_registry(_db, scope, key):
        if scope == REG_PERSONAL:
            return None
        if key == str(dept_id):
            return dept_reg
        if scope == "company":
            return company_reg
        return None

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._get_registry",
        side_effect=_get_registry,
    ), patch(
        "app.services.ragflow_scope_service._registry_scope_for_dept",
        return_value="department",
    ), patch(
        "app.services.ragflow_scope_service._dept_ids_for_kb_access",
        return_value=[dept_id],
    ), patch(
        "app.services.ragflow_scope_service._dataset_ids_for_explicit_non_personal_shares",
        return_value=set(),
    ):
        allowed = allowed_dataset_ids_for_user(db, user)

    assert allowed == {"ds-dept"}


def test_allowed_dataset_ids_only_includes_own_personal():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    own = MagicMock(ragflow_dataset_id="ds-own", scope=REG_PERSONAL, scope_key=str(user.id))
    other = MagicMock(
        ragflow_dataset_id="ds-other",
        scope=REG_PERSONAL,
        scope_key=str(uuid.uuid4()),
    )

    def _get_registry(_db, scope, key):
        if scope == REG_PERSONAL and key == str(user.id):
            return own
        if scope == REG_PERSONAL:
            return other
        return None

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=True,
    ), patch(
        "app.services.ragflow_scope_service._get_registry",
        side_effect=_get_registry,
    ), patch(
        "app.services.ragflow_scope_service._dept_ids_for_kb_access",
        return_value=[],
    ), patch(
        "app.services.ragflow_scope_service._dataset_ids_for_explicit_non_personal_shares",
        return_value=set(),
    ):
        allowed = allowed_dataset_ids_for_user(db, user)

    assert allowed == {"ds-own"}


def test_explicit_shares_allowed_ids_skip_other_personal_kb():
    from app.services.ragflow_scope_service import allowed_dataset_ids_for_user

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._get_registry",
        return_value=None,
    ), patch(
        "app.services.ragflow_scope_service._dept_ids_for_kb_access",
        return_value=[],
    ), patch(
        "app.services.ragflow_scope_service._dataset_ids_for_explicit_non_personal_shares",
        return_value={"ds-dept"},
    ):
        allowed = allowed_dataset_ids_for_user(db, user)

    assert allowed == {"ds-dept"}


def test_revoke_other_users_personal_kb_grants():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4(), username="qiu")
    link = MagicMock(ragflow_user_id="rag-qiu")
    own = MagicMock(
        ragflow_dataset_id="ds-own",
        scope=REG_PERSONAL,
        scope_key=str(user.id),
    )
    other = MagicMock(
        ragflow_dataset_id="ds-zhang",
        scope=REG_PERSONAL,
        scope_key=str(uuid.uuid4()),
    )
    db.scalars.return_value.all.return_value = [own, other]

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_scope_service.revoke_kb_user_permission",
        return_value=True,
    ) as revoke:
        from app.services.ragflow_scope_service import revoke_other_users_personal_kb_grants

        count = revoke_other_users_personal_kb_grants(db, user)

    assert count == 1
    revoke.assert_called_once_with("ds-zhang", "rag-qiu")


def test_revoke_unauthorized_kb_grants_skips_allowed():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    link = MagicMock(ragflow_user_id="rag-1")

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value={"ds-own"},
    ), patch(
        "app.services.ragflow_scope_service._revoke_candidate_dataset_ids",
        return_value={"ds-own", "ds-other"},
    ), patch(
        "app.services.ragflow_scope_service.revoke_kb_user_permission",
        return_value=True,
    ) as revoke:
        count = revoke_unauthorized_kb_grants(db, user)

    assert count == 1
    revoke.assert_called_once_with("ds-other", "rag-1")


def test_revoke_unauthorized_kb_grants_uses_ragflow_visible_list():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    link = MagicMock(ragflow_user_id="rag-1")
    kf = MagicMock()
    kf.enabled.return_value = True

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value={"ds-own"},
    ), patch(
        "app.services.ragflow_scope_service._revoke_candidate_dataset_ids",
        return_value={"ds-own", "ds-stale-visible"},
    ) as candidates, patch(
        "app.services.ragflow_scope_service.revoke_kb_user_permission",
        return_value=True,
    ) as revoke:
        count = revoke_unauthorized_kb_grants(db, user, kf=kf)

    candidates.assert_called_once_with(db, user, kf)
    assert count == 1
    revoke.assert_called_once_with("ds-stale-visible", "rag-1")
