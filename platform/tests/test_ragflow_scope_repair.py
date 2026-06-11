"""分级知识库登记修复与 mapped 模式建库。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.ragflow_scope_service import (
    _provision_rag_for_scope,
    repair_stale_scope_registries,
)
from app.core.document_scope import SCOPE_DEPARTMENT


def test_repair_stale_keeps_bootstrap_dept_registry():
    db = MagicMock()
    dept_reg = MagicMock(ragflow_dataset_id="ds-dept-bootstrap")
    db.scalars.return_value.all.return_value = [dept_reg]

    with patch(
        "app.services.ragflow_scope_service._live_knowflow_dataset_ids",
        return_value={"ds-dept-bootstrap", "ds-other"},
    ):
        removed = repair_stale_scope_registries(db, MagicMock())

    assert removed == 0
    db.delete.assert_not_called()


def test_repair_stale_removes_truly_missing_registry():
    db = MagicMock()
    stale = MagicMock(ragflow_dataset_id="ds-gone")
    db.scalars.return_value.all.return_value = [stale]

    with patch(
        "app.services.ragflow_scope_service._live_knowflow_dataset_ids",
        return_value={"ds-live"},
    ):
        removed = repair_stale_scope_registries(db, MagicMock())

    assert removed == 1
    db.delete.assert_called_once_with(stale)


def test_provision_rag_for_dept_uses_privileged_client_in_mapped_mode():
    db = MagicMock()
    actor = MagicMock()
    kf = MagicMock()
    kf.enabled.return_value = True
    user_rag = MagicMock()
    kf._rag = user_rag
    priv = MagicMock()

    with patch(
        "app.services.ragflow_scope_service._is_mapped_account_mode",
        return_value=True,
    ), patch(
        "app.services.ragflow_scope_service._privileged_rag_client",
        return_value=priv,
    ):
        client = _provision_rag_for_scope(db, actor, SCOPE_DEPARTMENT, kf)

    assert client is priv
