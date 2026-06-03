"""清理未登记 KnowFlow 知识库。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.ragflow_scope_service import purge_unregistered_knowledge_bases


def test_purge_unregistered_deletes_orphan_dataset():
    reg = MagicMock(
        ragflow_dataset_id="registered-ds",
        scope="department",
        scope_key="dept-1",
    )
    kf = MagicMock()
    kf.enabled.return_value = True
    kf._rag.list_datasets.return_value = [
        {"id": "registered-ds", "name": "咨询服务部"},
        {"id": "orphan-ds", "name": "部门"},
    ]

    db = MagicMock()
    db.scalars.return_value.all.side_effect = [
        [reg],
        [reg],
    ]

    with patch(
        "app.services.ragflow_scope_service._alias_names_for_registry",
        return_value={"咨询服务部"},
    ):
        removed = purge_unregistered_knowledge_bases(db, kf)

    assert removed == 1
    kf._rag.delete_dataset.assert_called_once_with("orphan-ds")
