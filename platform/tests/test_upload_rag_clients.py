"""KnowFlow 上传客户端选择。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.ragflow_sync_service import _upload_rag_clients


def test_upload_rag_clients_prefers_provision_client_in_mapped_mode():
    db = MagicMock()
    actor = MagicMock()
    document = MagicMock()
    kf = MagicMock()

    provision = MagicMock(name="provision_rag")
    user_rag = MagicMock(name="user_rag")
    priv = MagicMock(name="priv_rag")
    kf._rag = user_rag

    with patch(
        "app.services.ragflow_scope_service._provision_rag_for_scope",
        return_value=provision,
    ), patch(
        "app.services.ragflow_scope_service._privileged_rag_client",
        return_value=priv,
    ), patch(
        "app.services.ragflow_scope_service._admin_rag_client",
        return_value=None,
    ), patch(
        "app.services.ragflow_sync_service._document_scope",
        return_value="department",
    ):
        clients = _upload_rag_clients(db, actor=actor, document=document, kf=kf)

    assert clients[0] is provision
    assert user_rag in clients
    assert priv in clients
