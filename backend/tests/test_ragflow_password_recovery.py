"""RAGFlow 密码不一致时的恢复逻辑。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.integrations.ragflow_provision import (
    _password_mismatch_message,
    provision_and_login,
    recover_ragflow_account,
)
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink


def test_password_mismatch_detection():
    assert _password_mismatch_message("Email and password do not match!")
    assert not _password_mismatch_message("network error")


def test_uid_suffix_from_platform_email():
    from app.integrations.ragflow_provision import _uid_suffix_from_platform_email

    assert _uid_suffix_from_platform_email("u-84bfc14a@platform.local") == "84bfc14a"
    assert _uid_suffix_from_platform_email("alice-caf46c9d@platform.local") == "caf46c9d"
    assert _uid_suffix_from_platform_email("bad@example.com") is None


def test_recover_clears_and_relogins():
    user = User(
        id=uuid.uuid4(),
        username="alice",
        email="alice@corp.com",
        password_hash="x",
        display_name="Alice",
    )
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email="alice@platform.local",
        ragflow_password="old",
        ragflow_user_id="stale",
    )
    with patch(
        "app.integrations.ragflow_provision._purge_ragflow_user_by_email",
        return_value=True,
    ), patch(
        "app.integrations.ragflow_provision._register_user",
        return_value=None,
    ), patch(
        "app.integrations.ragflow_provision._login_user",
        return_value="new-jwt",
    ), patch(
        "app.integrations.ragflow_provision.finalize_ragflow_link"
    ) as finalize:
        token = recover_ragflow_account(link, user)
    assert token == "new-jwt"
    assert link.ragflow_password != "old"
    finalize.assert_called_once_with(link, "new-jwt", user)


def test_provision_retries_on_password_mismatch():
    user = User(
        id=uuid.uuid4(),
        username="bob",
        email="bob@corp.com",
        password_hash="x",
        display_name="Bob",
    )
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email="bob@platform.local",
        ragflow_password="secret",
    )
    from app.integrations.ragflow_provision import RagflowProvisionError

    with patch(
        "app.integrations.ragflow_provision._login_user",
        side_effect=[
            RagflowProvisionError("Email and password do not match!"),
        ],
    ), patch(
        "app.integrations.ragflow_provision.recover_ragflow_account",
        return_value="jwt-ok",
    ) as recover, patch(
        "app.integrations.ragflow_provision._register_user"
    ), patch(
        "app.integrations.ragflow_provision.ensure_shared_llm_config"
    ), patch(
        "app.integrations.ragflow_provision.ensure_ragflow_global_admin"
    ), patch(
        "app.integrations.ragflow_provision._fetch_ragflow_user_id",
        return_value="u1",
    ):
        token = provision_and_login(link, user)
    assert token == "jwt-ok"
    recover.assert_called_once()
