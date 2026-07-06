"""回收站彻底删除。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.document import Document, DocumentStatus, DocumentVersion


def test_empty_recycle_bin(client, admin_token):
    c = client
    h = {"Authorization": f"Bearer {admin_token}"}
    title = f"purge-test-{uuid.uuid4().hex[:8]}"
    r = c.post(
        "/api/v1/documents",
        headers=h,
        json={"title": title, "scope": "personal"},
    )
    assert r.status_code == 200, r.text
    did = r.json()["data"]["id"]
    c.delete(f"/api/v1/documents/{did}", headers=h)
    r2 = c.post("/api/v1/documents/trash/empty", headers=h)
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]
    assert data["ok"] is True
    assert data["count"] >= 1
    trash = c.get("/api/v1/documents/trash", headers=h).json()["data"]
    assert did not in {item["id"] for item in trash["items"]}


def test_purge_clears_versions():
    from unittest.mock import patch

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.services.document_service import purge_document_completely

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "admin"))
        doc = Document(
            title="ver-purge",
            owner_id=user.id,
            scope="personal",
            status=DocumentStatus.active.value,
            deleted_at=datetime.now(timezone.utc),
            deleted_by=user.id,
        )
        db.add(doc)
        db.flush()
        ver = DocumentVersion(
            document_id=doc.id,
            version_no=1,
            file_name="a.pdf",
            file_size=100,
            file_key="k/a.pdf",
            mime_type="application/pdf",
            created_by=user.id,
        )
        db.add(ver)
        db.flush()
        doc.current_version_id = ver.id
        db.commit()

        with patch(
            "app.services.ragflow_sync_service.remove_platform_document_from_knowflow",
            return_value=False,
        ):
            purge_document_completely(db, doc)
        db.commit()

        assert db.get(Document, doc.id) is None
        assert db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
        ) is None
    finally:
        db.close()
