"""平台运行大屏统计逻辑测试。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.services.platform_dashboard_service import (
    RAGFLOW_RUN_COMPLETED,
    _count_documents_indexed,
    _fetch_run_status_map,
    _indexed_doc_ids_from_version_links,
)


class _FakeRag:
    def __init__(self, docs_by_page: dict[int, list[dict]], total: int):
        self.docs_by_page = docs_by_page
        self.total = total

    def list_dataset_documents(self, dataset_id, *, page=1, page_size=30, keywords=None):
        docs = self.docs_by_page.get(page, [])
        return docs, self.total


def test_fetch_run_status_map_paginates():
    rag = _FakeRag(
        {
            1: [{"id": "a", "run": RAGFLOW_RUN_COMPLETED}],
            2: [{"id": "b", "run": "4"}],
        },
        total=60,
    )
    result = _fetch_run_status_map(rag, "ds1", {"a", "b"})
    assert result == {"a": RAGFLOW_RUN_COMPLETED, "b": "4"}


def test_count_documents_indexed_excludes_failed(monkeypatch):
    doc_ok = uuid.uuid4()
    doc_fail = uuid.uuid4()
    link_rows = [
        (doc_ok, "rag-ok", "ds1"),
        (doc_fail, "rag-fail", "ds1"),
    ]

    db = MagicMock()

    def _execute_side_effect(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "index_completed_at" in sql:
            result.all.return_value = []
        elif "ragflow_document_version_links" in sql:
            result.all.return_value = link_rows
        elif "ragflow_document_links" in sql:
            result.all.return_value = link_rows
        else:
            result.all.return_value = []
        return result

    db.execute.side_effect = _execute_side_effect

    fake_rag = MagicMock()
    fake_rag.health_ok.return_value = True
    fake_rag.list_dataset_documents.return_value = (
        [
            {"id": "rag-ok", "run": RAGFLOW_RUN_COMPLETED},
            {"id": "rag-fail", "run": "4"},
        ],
        2,
    )

    monkeypatch.setattr(
        "app.domains.knowledge.gateway.knowledge.stack_reachable",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.ragflow_scope_service._privileged_rag_client",
        lambda _db: fake_rag,
    )

    assert _count_documents_indexed(db) == 1


def test_count_documents_indexed_uses_version_link_without_knowflow(monkeypatch):
    doc_id = uuid.uuid4()
    db = MagicMock()

    def _execute_side_effect(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "index_completed_at" in sql:
            result.all.return_value = [(doc_id,)]
        else:
            result.all.return_value = []
        return result

    db.execute.side_effect = _execute_side_effect

    monkeypatch.setattr(
        "app.domains.knowledge.gateway.knowledge.stack_reachable",
        lambda: False,
    )

    assert _indexed_doc_ids_from_version_links(db) == {doc_id}
    assert _count_documents_indexed(db) == 1
