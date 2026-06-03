"""删除用户时清理文档与 KnowFlow 资源。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.user_knowflow_purge import purge_user_knowledge_resources


def test_purge_user_owned_documents_and_mirrors():
    uid = uuid.uuid4()
    user = MagicMock(id=uid, username="tester")
    doc = MagicMock(id=uuid.uuid4(), owner_id=uid)
    mirror = MagicMock(
        platform_document_id=doc.id,
        platform_user_id=uid,
        dataset_id="ds-1",
        ragflow_document_id="rag-1",
    )

    db = MagicMock()
    db.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=[mirror])),
        MagicMock(all=MagicMock(return_value=[doc.id])),
        MagicMock(all=MagicMock(return_value=[doc])),
    ]
    db.get.return_value = doc
    db.scalar.return_value = None

    with patch(
        "app.services.user_knowflow_purge.get_settings",
    ) as gs, patch(
        "app.services.ragflow_sync_service.remove_document_mirror",
        return_value=True,
    ) as rm_mirror, patch(
        "app.services.user_knowflow_purge.purge_document_completely",
    ) as purge_doc, patch(
        "app.services.user_knowflow_purge.delete",
    ):
        gs.return_value.knowflow_enabled = False
        out = purge_user_knowledge_resources(db, user)

    assert out["documents_purged"] == 1
    rm_mirror.assert_called_once()
    purge_doc.assert_called_once_with(db, doc)
