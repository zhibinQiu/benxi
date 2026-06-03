"""入库后立即同步 KnowFlow 的编排。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domains.knowledge import gateway as kg


def test_sync_document_after_ingest_prepares_account_and_catalog():
    db = MagicMock()
    user = MagicMock(username="alice")
    doc = MagicMock(id="doc-1")

    with (
        patch.object(kg.KnowledgeGateway, "enabled", return_value=True),
        patch.object(kg.KnowledgeGateway, "user_auth", return_value="jwt") as auth,
        patch.object(kg.KnowledgeGateway, "reconcile_catalog") as reconcile,
        patch.object(
            kg.KnowledgeGateway, "sync_document", return_value="rag-doc-1"
        ) as sync,
    ):
        rid = kg.knowledge.sync_document_after_ingest(db, user, doc)

    assert rid == "rag-doc-1"
    auth.assert_called_once_with(db, user)
    reconcile.assert_called_once_with(db, user, sync_documents=False)
    sync.assert_called_once_with(db, user, doc, force=True)


def test_sync_document_after_ingest_skips_when_auth_missing():
    db = MagicMock()
    user = MagicMock(username="bob")
    doc = MagicMock(id="doc-2")

    with (
        patch.object(kg.KnowledgeGateway, "enabled", return_value=True),
        patch.object(kg.KnowledgeGateway, "user_auth", return_value=None),
        patch.object(kg.KnowledgeGateway, "reconcile_catalog") as reconcile,
        patch.object(kg.KnowledgeGateway, "sync_document") as sync,
    ):
        rid = kg.knowledge.sync_document_after_ingest(db, user, doc)

    assert rid is None
    reconcile.assert_not_called()
    sync.assert_not_called()
