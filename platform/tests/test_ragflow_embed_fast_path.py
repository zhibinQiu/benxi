"""embed-session SSO 快路径。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.ragflow_identity_service import (
    _knowflow_catalog_ready,
    build_embed_session,
)


def test_knowflow_catalog_ready_with_personal_or_dept_registry():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    link = MagicMock(ragflow_user_id="rag-user-1")
    dept_id = uuid.uuid4()

    with patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._dept_ids_for_kb_access",
        return_value=[dept_id],
    ), patch(
        "app.services.ragflow_scope_service._get_registry",
        return_value=MagicMock(ragflow_dataset_id="ds-dept"),
    ), patch(
        "app.services.ragflow_scope_service._registry_scope_for_dept",
        return_value="department",
    ):
        assert _knowflow_catalog_ready(db, user, link) is True

    with patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=True,
    ):
        assert _knowflow_catalog_ready(db, user, link) is True


def test_knowflow_catalog_ready_requires_personal_dataset():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    link = MagicMock(ragflow_user_id="rag-user-1")

    with patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._dept_ids_for_kb_access",
        return_value=[],
    ):
        assert _knowflow_catalog_ready(db, user, link) is False


def test_build_embed_session_skips_reconcile_when_catalog_ready():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4(), username="alice", display_name="Alice")
    link = MagicMock(
        ragflow_user_id="rag-user-1",
        ragflow_email="u@test.local",
        ragflow_access_token="Bearer cached",
    )
    personal = MagicMock(ragflow_dataset_id="ds-personal-1")
    db.scalar.return_value = personal

    with (
        patch("app.services.ragflow_identity_service.get_settings") as gs,
        patch("app.services.ragflow_identity_service.get_or_create_link", return_value=link),
        patch(
            "app.services.ragflow_identity_service._ragflow_user_info",
            return_value=(True, {"nickname": "u", "email": "u@test.local"}),
        ),
        patch(
            "app.services.ragflow_identity_service._knowflow_catalog_ready",
            return_value=True,
        ),
        patch(
            "app.services.ragflow_identity_service.resolve_embed_ragflow_authorization",
            return_value=("Bearer cached", {"nickname": "u"}),
        ),
        patch(
            "app.services.ragflow_scope_service.knowflow_kb_labels_for_user",
            return_value=[],
        ),
        patch(
            "app.services.ragflow_scope_service.dept_suffix_labels_for_theme",
            return_value={},
        ),
        patch(
            "app.services.ragflow_identity_service.dataset_display_label_personal",
            return_value="我的",
        ),
        patch(
            "app.services.knowflow_catalog_service.reconcile_user_knowflow_catalog"
        ) as reconcile,
        patch(
            "app.services.knowflow_catalog_service.reconcile_user_knowflow_kb_acl"
        ) as reconcile_acl,
        patch(
            "app.integrations.ragflow_llm_template.ensure_shared_llm_config",
        ),
        patch(
            "app.core.permissions.user_is_system_admin",
            return_value=False,
        ),
        patch(
            "app.core.platform_admin.is_bootstrap_admin",
            return_value=False,
        ),
    ):
        settings = MagicMock(
            knowflow_enabled=True,
            knowflow_ui_url="http://127.0.0.1:9380",
            ragflow_sync_on_embed=False,
            knowflow_theme_app_name="ZT",
            app_name="ZT",
            knowflow_theme_primary="#000",
            knowflow_theme_primary_hover="#111",
            knowflow_theme_primary_pressed="#222",
            knowflow_hide_file_manager=True,
            knowflow_theme_logo_url="",
            knowflow_theme_favicon_url="",
        )
        gs.return_value = settings

        out = build_embed_session(db, user, sync_catalog=False)

    assert out["sso"]["ready"] is True
    assert out["sso"]["authorization"] == "Bearer cached"
    reconcile.assert_not_called()
    reconcile_acl.assert_called_once()
