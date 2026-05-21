"""Translate document library integration tests."""

from __future__ import annotations

import uuid


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_translatable_documents_requires_auth(client):
    r = client.get("/api/v1/translate/documents")
    assert r.status_code == 401


def test_list_translatable_documents_ok(client, admin_token):
    r = client.get("/api/v1/translate/documents", headers=_auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert "total" in data


def test_create_job_requires_source(client, admin_token):
    r = client.post(
        "/api/v1/translate/jobs",
        headers=_auth(admin_token),
        data={"lang_in": "en", "lang_out": "zh-CN", "service": "siliconflow"},
    )
    assert r.status_code == 400


def test_create_job_rejects_unknown_document(client, admin_token):
    r = client.post(
        "/api/v1/translate/jobs",
        headers=_auth(admin_token),
        data={
            "document_id": str(uuid.uuid4()),
            "lang_in": "en",
            "lang_out": "zh-CN",
            "service": "siliconflow",
        },
    )
    assert r.status_code in (400, 404)
