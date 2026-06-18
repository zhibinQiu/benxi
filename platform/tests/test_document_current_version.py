"""current_version_id 缺失时仍可下载。"""

from __future__ import annotations

from app.database import SessionLocal
from app.models.document import Document
from test_support.document_upload import upload_dummy_pdf


def test_resolve_current_version_repairs_null_pointer(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "repair-current", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    upload_dummy_pdf(client, doc_id, headers)

    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        doc.current_version_id = None
        db.commit()

    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["current_version_id"] is not None
    assert any(v["is_current"] and v["uploaded"] for v in data["versions"])

    dl = client.get(f"/api/v1/documents/{doc_id}/file", headers=headers)
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF")
