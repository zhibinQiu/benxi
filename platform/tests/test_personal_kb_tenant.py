"""个人库必须绑定用户 mapped 租户，不可误用 bootstrap 他人库。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import SCOPE_PERSONAL
from app.models.ragflow_scope_dataset import SCOPE_PERSONAL as REG_PERSONAL
from app.services.ragflow_scope_service import (
    _provision_rag_for_scope,
    _resolve_personal_dataset_id,
    _user_has_personal_kb,
)


def test_provision_rag_for_personal_uses_privileged_in_mapped_mode():
    db = MagicMock()
    actor = MagicMock(id=uuid.uuid4())
    catalog_kf = MagicMock()
    catalog_kf.enabled.return_value = True
    catalog_kf._rag = MagicMock(name="bootstrap_rag")
    user_kf = MagicMock()
    user_kf.enabled.return_value = True
    user_kf._rag = MagicMock(name="user_rag")

    with patch(
        "app.services.ragflow_scope_service._is_mapped_account_mode",
        return_value=True,
    ), patch(
        "app.services.ragflow_scope_service._privileged_rag_client",
        return_value=catalog_kf._rag,
    ):
        rag = _provision_rag_for_scope(db, actor, SCOPE_PERSONAL, catalog_kf)

    assert rag is catalog_kf._rag


def test_resolve_personal_rejects_registry_outside_user_tenant():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    wrong_reg = MagicMock(ragflow_dataset_id="ds-bootstrap-other")

    with patch(
        "app.services.ragflow_scope_service._get_registry",
        return_value=wrong_reg,
    ), patch(
        "app.services.ragflow_scope_service._personal_dataset_in_user_tenant",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._is_mapped_account_mode",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_knowflow_client"
    ) as user_kf_mock, patch(
        "app.services.ragflow_scope_service.dataset_name_for_personal",
        return_value="zt-personal-test",
    ), patch(
        "app.services.ragflow_scope_service.legacy_dataset_name_for_personal",
        return_value="zt-personal-legacy",
    ), patch(
        "app.services.ragflow_scope_service.legacy_dataset_name_for_platform_user",
        return_value="zt-platform-legacy",
    ), patch(
        "app.services.ragflow_scope_service.dataset_display_label_personal",
        return_value="测试",
    ):
        user_kf = MagicMock()
        user_kf.enabled.return_value = True
        user_kf._rag.find_dataset_by_names.return_value = None
        user_kf_mock.return_value = user_kf
        ds = _resolve_personal_dataset_id(db, user)

    assert ds is None
    db.delete.assert_called_once_with(wrong_reg)


def test_user_has_personal_kb_requires_user_tenant():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    reg = MagicMock(ragflow_dataset_id="ds-1")

    with patch(
        "app.services.ragflow_scope_service._get_registry",
        return_value=reg,
    ), patch(
        "app.services.ragflow_scope_service._personal_dataset_in_user_tenant",
        side_effect=[False, True],
    ):
        assert _user_has_personal_kb(db, user) is False
        assert _user_has_personal_kb(db, user) is True
