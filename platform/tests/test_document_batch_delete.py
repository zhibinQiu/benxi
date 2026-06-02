"""批量删除文档。"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.models.job import Job, JobStatus, JobType


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

    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalar(
            __import__("sqlalchemy").select(User).where(User.username == "admin")
        )
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
        "app.services.ragflow_sync_service.remove_platform_document_from_knowflow",
        return_value=False,
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
