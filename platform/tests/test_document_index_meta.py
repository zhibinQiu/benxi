"""文档索引状态：RAGFlow 元数据拉取与展示合并。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.ragflow_client import RagflowError
from app.services.document_index_service import (
    _apply_cached_ragflow_meta,
    _meta_from_version_link,
    _merge_enriched_row,
)
from app.services.knowledge_library_service import (
    _apply_row_ragflow_meta,
    fetch_ragflow_doc_meta_map,
    summarize_ragflow_progress_msg,
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


def test_summarize_ragflow_progress_msg_extracts_model_disabled():
    msg = (
        "08:56:40 Page(1~13): Basic parsing complete. Proceeding with figure enhancement...\n"
        "08:56:26 Page(1~4): [ERROR]Error code: 403 - "
        "{'code': 30003, 'message': 'Model disabled.', 'data': None}"
    )
    out = summarize_ragflow_progress_msg(msg)
    assert out is not None
    assert "Model disabled" in out or "403" in out


def test_summarize_ragflow_progress_msg_prefers_embedding_bind_error():
    msg = (
        "17:30:42 Task has been received.\n"
        "17:30:47 Page(1~100000001): [ERROR]Fail to bind embedding model: Not Found\n"
        "17:30:47 [ERROR][Exception]: Not Found"
    )
    out = summarize_ragflow_progress_msg(msg)
    assert out is not None
    assert "embedding" in out.lower() or "嵌入" in out


def test_transient_run_not_cached(monkeypatch):
    from app.services.knowledge_library_service import (
        _read_ragflow_meta_cache,
        _write_ragflow_meta_cache,
    )

    writes: list[dict] = []
    monkeypatch.setattr(
        "app.core.platform_cache.cache_set_json",
        lambda key, val, ttl: writes.append(val),
    )
    monkeypatch.setattr(
        "app.core.platform_cache.cache_get_json",
        lambda key, ttl: writes[-1] if writes else None,
    )
    _write_ragflow_meta_cache("ds-1", "doc-a", {"run": "1", "progress": 0.5})
    assert writes == []
    _write_ragflow_meta_cache("ds-1", "doc-b", {"run": "4", "progress": -1})
    assert len(writes) == 1
    assert _read_ragflow_meta_cache("ds-1", "doc-b") is not None
    monkeypatch.setattr(
        "app.core.platform_cache.cache_get_json",
        lambda key, ttl: {"run": "1", "progress": 0.2},
    )
    assert _read_ragflow_meta_cache("ds-1", "doc-c") is None


def test_fetch_meta_overlays_mysql_run_when_cache_stale(monkeypatch):
    from app.services.knowledge_library_service import (
        _write_ragflow_meta_cache,
        fetch_ragflow_doc_meta_map,
        _apply_row_ragflow_meta,
    )

    monkeypatch.setattr(
        "app.services.knowledge_library_service._knowflow_ready",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.knowledge_library_service._rag_clients_for_user",
        lambda _db, _user: [],
    )
    _write_ragflow_meta_cache(
        "ds-1",
        "doc-a",
        {"run": "1", "progress": 0.5, "chunk_num": 0},
    )
    monkeypatch.setattr(
        "app.services.knowledge_library_service._fetch_document_run_map_from_mysql",
        lambda _db, ids: {
            "doc-a": {
                "run": "4",
                "progress": -1.0,
                "progress_msg": "Visual model failed",
                "chunk_num": 11,
            }
        },
    )
    db = MagicMock()
    user = MagicMock()
    meta, ok = fetch_ragflow_doc_meta_map(db, user, "ds-1", ["doc-a"])
    row = {}
    _apply_row_ragflow_meta(row, meta.get("doc-a"), fetch_ok=ok)
    assert row["parse_status"] == "解析失败"


def test_apply_cached_ragflow_meta_overrides_unparsed_db_label(monkeypatch):
    from app.models.ragflow_document_version_link import RagflowDocumentVersionLink

    link = RagflowDocumentVersionLink(
        ragflow_document_id="rag-doc-1",
        dataset_id="ds-1",
        version_no=1,
    )
    meta = _meta_from_version_link(link)
    assert meta["parse_status"] == "未解析"

    def fake_read(_ds, _rid):
        return {"run": "4", "progress_msg": "Visual model failed", "chunk_num": 0}

    monkeypatch.setattr(
        "app.services.knowledge_library_service._read_ragflow_meta_cache",
        fake_read,
    )
    _apply_cached_ragflow_meta(meta, "ds-1", "rag-doc-1")
    assert meta["parse_status"] == "解析失败"


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
        "app.services.knowledge_library_service._read_ragflow_meta_cache",
        return_value=None,
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
