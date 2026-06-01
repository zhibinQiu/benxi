"""KnowFlow 目录对齐服务。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowflow_catalog_service import reconcile_user_knowflow_catalog


def test_reconcile_skips_when_disabled():
    db = MagicMock()
    user = MagicMock()
    with patch("app.services.knowflow_catalog_service.get_settings") as gs:
        gs.return_value.knowflow_enabled = False
        out = reconcile_user_knowflow_catalog(db, user)
    assert out.get("ok") is False


def test_reconcile_calls_grant_and_sync():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    kf = MagicMock()
    kf.enabled.return_value = True
    call_order: list[str] = []

    def _mark(name):
        def _fn(*_a, **_k):
            call_order.append(name)

        return _fn

    with patch("app.services.knowflow_catalog_service.get_settings") as gs:
        gs.return_value.knowflow_enabled = True
        gs.return_value.ragflow_grant_global_admin = True
        gs.return_value.ragflow_sync_doc_limit = 10
        with patch(
            "app.services.knowflow_catalog_service.get_knowflow_client_for_user",
            return_value=kf,
        ), patch(
            "app.services.knowflow_catalog_service._ensure_ragflow_kb_admin"
        ), patch(
            "app.services.knowflow_catalog_service.repair_stale_scope_registries",
            return_value=1,
        ), patch(
            "app.services.knowflow_catalog_service._drop_orphan_document_links",
            return_value=0,
        ), patch(
            "app.services.knowflow_catalog_service.ensure_user_scope_datasets",
            side_effect=_mark("scope"),
        ), patch(
            "app.services.knowflow_catalog_service.sync_user_kb_grants",
            side_effect=lambda *_a, **_k: (call_order.append("grants"), 2)[1],
        ), patch(
            "app.services.knowflow_catalog_service.sync_accessible_documents",
            return_value={"a": "b"},
        ), patch(
            "app.services.knowflow_catalog_service._visible_dataset_ids",
            return_value={"ds1"},
        ):
            out = reconcile_user_knowflow_catalog(db, user, sync_limit=5)
    assert out["ok"] is True
    assert out["synced_documents"] == 1
    assert out["catalog_prepared"] is True
    assert call_order.index("scope") < call_order.index("grants")


def test_reconcile_prepare_only_skips_document_sync():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    kf = MagicMock()
    kf.enabled.return_value = True

    with patch("app.services.knowflow_catalog_service.get_settings") as gs:
        gs.return_value.knowflow_enabled = True
        gs.return_value.ragflow_grant_global_admin = True
        with patch(
            "app.services.knowflow_catalog_service.get_knowflow_client_for_user",
            return_value=kf,
        ), patch("app.services.knowflow_catalog_service._ensure_ragflow_kb_admin"), patch(
            "app.services.knowflow_catalog_service.repair_stale_scope_registries",
            return_value=0,
        ), patch(
            "app.services.knowflow_catalog_service._drop_orphan_document_links",
            return_value=0,
        ), patch(
            "app.services.knowflow_catalog_service.ensure_user_scope_datasets"
        ) as scope, patch(
            "app.services.knowflow_catalog_service.sync_user_kb_grants",
            return_value=1,
        ), patch(
            "app.services.knowflow_catalog_service.sync_accessible_documents"
        ) as doc_sync, patch(
            "app.services.knowflow_catalog_service._visible_dataset_ids",
            return_value={"ds1", "ds2"},
        ):
            out = reconcile_user_knowflow_catalog(
                db, user, sync_documents=False
            )
    scope.assert_called_once()
    doc_sync.assert_not_called()
    assert out["synced_documents"] == 0
    assert out["visible_datasets"] == 2
