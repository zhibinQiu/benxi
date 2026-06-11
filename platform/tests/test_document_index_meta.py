"""文档索引状态：RAGFlow 元数据拉取与展示合并。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.ragflow_client import RagflowError
from app.services.document_index_service import _merge_enriched_row
from app.services.knowledge_library_service import (
    _apply_row_ragflow_meta,
    fetch_ragflow_doc_meta_map,
)


def test_merge_enriched_row_does_not_fake_parsing_when_fetch_failed():
    meta = {"knowledge_synced": True, "parse_status": None}
    _merge_enriched_row(
        meta,
        {"_meta_fetch_ok": False, "parse_status": None},
    )
    assert meta["parse_status"] is None


def test_merge_enriched_row_marks_stale_when_synced_but_missing_in_ragflow():
    meta = {"knowledge_synced": True, "parse_status": None}
    _merge_enriched_row(
        meta,
        {"_meta_fetch_ok": True, "parse_status": None},
    )
    assert meta["parse_status"] == "索引失效"


def test_apply_row_ragflow_meta_maps_failed_run():
    row: dict = {}
    _apply_row_ragflow_meta(
        row,
        {
            "run": 4,
            "progress_msg": "Visual model failed",
            "chunk_num": 0,
        },
        fetch_ok=True,
    )
    assert row["parse_status"] == "解析失败"
    assert "Visual model failed" in row["parse_message"]


def test_fetch_ragflow_doc_meta_map_falls_back_to_chunk_list():
    db = MagicMock()
    user = MagicMock()
    rag = MagicMock()
    rag.health_ok.return_value = True
    rag.list_dataset_documents.side_effect = RagflowError('Lack of "KB ID"')
    rag.get_document_meta.return_value = {
        "run": "3",
        "chunk_num": 12,
        "progress": 1.0,
    }

    with patch(
        "app.services.knowledge_library_service._knowflow_ready",
        return_value=True,
    ), patch(
        "app.services.knowledge_library_service._rag_clients_for_user",
        return_value=[rag],
    ), patch(
        "app.services.knowledge_library_service._dataset_visible",
        return_value=True,
    ):
        meta, ok = fetch_ragflow_doc_meta_map(
            db, user, "ds-1", ["doc-a"]
        )

    assert ok is True
    assert meta["doc-a"]["run"] == "3"
    rag.get_document_meta.assert_called_once_with("ds-1", "doc-a")
