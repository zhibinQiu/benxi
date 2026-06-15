"""系统管理员切片管理应共用 bootstrap KnowFlow 会话。"""

from unittest.mock import MagicMock, patch
import uuid

from app.services.ragflow_identity_service import resolve_embed_ragflow_authorization


def test_sys_admin_gets_bootstrap_embed_auth():
    db = MagicMock()
    admin = MagicMock()
    admin.username = "zhang"
    bootstrap = MagicMock()
    bootstrap.username = "bootstrap"

    boot_auth = "bootstrap-jwt"
    boot_profile = {"access_token": "tok", "nickname": "系统管理员"}

    with patch(
        "app.core.permissions.user_is_system_admin",
        return_value=True,
    ), patch(
        "app.core.platform_admin.is_bootstrap_admin",
        return_value=False,
    ), patch(
        "app.core.phone.bootstrap_login_id",
        return_value="admin",
    ), patch(
        "app.services.ragflow_identity_service.select",
    ), patch(
        "app.services.ragflow_identity_service.get_user_ragflow_auth",
        return_value=boot_auth,
    ), patch(
        "app.services.ragflow_identity_service._ragflow_auth_valid",
        return_value=True,
    ), patch(
        "app.services.ragflow_identity_service._ragflow_user_info",
        return_value=(True, boot_profile),
    ):
        db.scalar.return_value = bootstrap
        auth, profile = resolve_embed_ragflow_authorization(
            db,
            admin,
            user_auth="own-jwt",
            user_profile={"nickname": "张海光"},
        )

    assert auth == boot_auth
    assert profile == boot_profile


def test_bootstrap_admin_keeps_own_embed_auth():
    db = MagicMock()
    user = MagicMock()

    with patch(
        "app.core.permissions.user_is_system_admin",
        return_value=True,
    ), patch(
        "app.core.platform_admin.is_bootstrap_admin",
        return_value=True,
    ):
        auth, profile = resolve_embed_ragflow_authorization(
            db,
            user,
            user_auth="own-jwt",
            user_profile={"nickname": "系统管理员"},
        )

    assert auth == "own-jwt"
    assert profile == {"nickname": "系统管理员"}


def test_member_keeps_own_embed_auth_when_catalog_empty():
    db = MagicMock()
    member = MagicMock()
    member.username = "member"

    boot_auth = "bootstrap-jwt"
    boot_profile = {"nickname": "系统管理员"}

    with patch(
        "app.core.platform_admin.is_bootstrap_admin",
        return_value=False,
    ), patch(
        "app.core.permissions.user_is_system_admin",
        return_value=False,
    ), patch(
        "app.services.ragflow_identity_service._embed_catalog_empty",
        return_value=True,
    ), patch(
        "app.services.ragflow_identity_service._bootstrap_embed_auth",
        return_value=(boot_auth, boot_profile),
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value={"ds-dept"},
    ):
        auth, profile = resolve_embed_ragflow_authorization(
            db,
            member,
            user_auth="own-jwt",
            user_profile={"nickname": "成员"},
        )

    assert auth == "own-jwt"
    assert profile == {"nickname": "成员"}


def test_member_keeps_own_auth_when_no_allowed_kbs():
    db = MagicMock()
    member = MagicMock()
    member.username = "member"

    boot_auth = "bootstrap-jwt"
    boot_profile = {"nickname": "系统管理员"}

    with patch(
        "app.core.platform_admin.is_bootstrap_admin",
        return_value=False,
    ), patch(
        "app.core.permissions.user_is_system_admin",
        return_value=False,
    ), patch(
        "app.services.ragflow_identity_service._embed_catalog_empty",
        return_value=True,
    ), patch(
        "app.services.ragflow_identity_service._bootstrap_embed_auth",
        return_value=(boot_auth, boot_profile),
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value=set(),
    ):
        auth, profile = resolve_embed_ragflow_authorization(
            db,
            member,
            user_auth="own-jwt",
            user_profile={"nickname": "成员"},
        )

    assert auth == "own-jwt"
    assert profile == {"nickname": "成员"}
