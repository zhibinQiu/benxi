"""平台原生切片库管理 API。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest


def test_knowledge_libraries_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/knowledge/libraries", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "items" in body
    assert "knowflow_enabled" in body


def test_knowledge_library_documents_forbidden(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    monkeypatch.setattr(
        "app.services.knowledge_library_service.allowed_dataset_ids_for_user",
        lambda db, user: set(),
    )
    r = client.get(
        "/api/v1/knowledge/libraries/ds-other/documents",
        headers=headers,
    )
    assert r.status_code == 403


def test_knowledge_document_chunks_requires_sync(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    doc_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.services.knowledge_library_service.get_document",
        lambda db, did: MagicMock(
            id=doc_id,
            title="测试文档",
            deleted_at=None,
            scope="personal",
        ),
    )
    monkeypatch.setattr(
        "app.services.knowledge_library_service.can_query_document",
        lambda db, user, doc: True,
    )
    monkeypatch.setattr(
        "app.services.knowledge_library_service._knowflow_ready",
        lambda: True,
    )

    class _Rag:
        def list_document_chunks(self, *args, **kwargs):
            return (
                [{"chunk_id": "c1", "content_with_weight": "片段内容", "page_num": 2}],
                1,
                {"chunk_count": 1},
            )

    class _Kf:
        def enabled(self):
            return True

        _rag = _Rag()

    monkeypatch.setattr(
        "app.services.knowledge_library_service.get_knowflow_client_for_user",
        lambda db, user: _Kf(),
    )

    r = client.get(
        f"/api/v1/knowledge/documents/{doc_id}/chunks",
        headers=headers,
    )
    assert r.status_code == 400


def test_knowledge_document_reindex_enqueues_job(
    client, admin_token, monkeypatch
):
    """重新索引须创建 document_index 后台任务并立即返回。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()

    mock_doc = MagicMock(id=doc_id, deleted_at=None, title="reindex-test")
    mock_version = MagicMock(id=version_id, document_id=doc_id, version_no=1)
    mock_job = MagicMock(id=job_id)

    monkeypatch.setattr(
        "app.services.knowledge_library_service.get_document",
        lambda db, did: mock_doc,
    )
    monkeypatch.setattr(
        "app.services.knowledge_library_service.can_query_document",
        lambda db, user, doc: True,
    )
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.knowledge.enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.knowledge.stack_reachable",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.ragflow_version_link_service.resolve_index_link",
        lambda db, doc, version_id=None: (None, mock_version),
    )

    enqueue_kwargs: dict = {}

    def fake_enqueue(db, **kwargs):
        enqueue_kwargs.update(kwargs)
        return mock_job

    monkeypatch.setattr(
        "app.services.knowledge_sync_job_service.enqueue_document_reindex",
        fake_enqueue,
    )

    r = client.post(
        f"/api/v1/knowledge/documents/{doc_id}/reindex",
        headers=headers,
        json={
            "version_id": str(version_id),
            "resync": True,
            "parser_id": "smart",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["queued"] is True
    assert body["knowledge_job_id"] == str(job_id)
    assert enqueue_kwargs.get("version_id") == version_id
    assert enqueue_kwargs.get("resync") is True
