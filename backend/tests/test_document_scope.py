"""文档库分级权限。"""

from __future__ import annotations

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_PERSONAL,
    can_create_in_scope,
    can_read_document,
)
from app.database import SessionLocal
from app.models.document import Document
from app.models.org import User
from sqlalchemy import select


def test_admin_can_create_company():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        assert can_create_in_scope(db, admin, SCOPE_COMPANY)
    finally:
        db.close()


def test_document_library_api(client, admin_token):
    r = client.get(
        "/api/v1/documents/library",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["folders"]) == 5
    scopes = [f["scope"] for f in data["folders"]]
    assert scopes == ["personal", "team", "department", "company", "shared"]


def test_list_all_scope_ok(client, admin_token):
    r = client.get(
        "/api/v1/documents?scope=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    if items:
        assert "effective_level" in items[0]


def test_create_personal_document(client, admin_token):
    r = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "scope-test-doc", "scope": "personal"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["scope"] == "personal"
