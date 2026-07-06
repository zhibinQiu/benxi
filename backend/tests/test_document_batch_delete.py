"""批量删除文档。"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.org import User


def _bootstrap_user(db):
    return db.scalar(select(User).where(User.phone == bootstrap_login_id()))


def test_batch_delete_with_related_job(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    title = f"batch-del-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": title, "scope": "personal"},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["data"]["id"]

    db = SessionLocal()
    try:
        user = _bootstrap_user(db)
        assert user is not None
        job = Job(
            type=JobType.pdf_translate.value,
            status=JobStatus.pending.value,
            document_id=uuid.UUID(doc_id),
            created_by=user.id,
            payload={"document_id": doc_id},
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    with patch(
        "app.services.ragflow_sync_service.schedule_knowflow_deletes",
    ), patch(
        "app.services.ragflow_sync_service._execute_knowflow_deletes",
    ):
        br = client.post(
            "/api/v1/documents/batch-delete",
            headers=headers,
            json={"document_ids": [doc_id], "permanent": True},
        )
    assert br.status_code == 200, br.text
    data = br.json()["data"]
    assert data["deleted_count"] == 1
    assert doc_id in data["deleted"]

    gone = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert gone.status_code == 404


def test_batch_delete_multiple_documents_schedules_async_external_purge(
    client, admin_token, monkeypatch,
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    doc_ids: list[str] = []
    for i in range(3):
        r = client.post(
            "/api/v1/documents",
            headers=headers,
            json={"title": f"batch-del-multi-{i}-{uuid.uuid4().hex[:6]}", "scope": "personal"},
        )
        assert r.status_code == 200, r.text
        doc_ids.append(r.json()["data"]["id"])

    scheduled: list[list[str]] = []

    def _track_schedule(document_ids):
        scheduled.append([str(doc_id) for doc_id in document_ids])

    monkeypatch.setattr(
        "app.services.documents.lifecycle.schedule_documents_external_purge",
        _track_schedule,
    )

    with patch(
        "app.services.ragflow_sync_service.schedule_knowflow_deletes",
    ), patch(
        "app.services.ragflow_sync_service._execute_knowflow_deletes",
    ):
        br = client.post(
            "/api/v1/documents/batch-delete",
            headers=headers,
            json={"document_ids": doc_ids, "permanent": True},
        )
    assert br.status_code == 200, br.text
    data = br.json()["data"]
    assert data["deleted_count"] == 3
    assert len(scheduled) == 1
    assert set(scheduled[0]) == set(doc_ids)
    for doc_id in doc_ids:
        gone = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert gone.status_code == 404
