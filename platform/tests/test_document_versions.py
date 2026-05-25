"""文档版本：初始占位与按版本删除。"""

from __future__ import annotations


def test_create_document_returns_initial_version(client, admin_token):
    r = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "version-init-doc", "scope": "personal"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["versions"]) == 1
    v = data["versions"][0]
    assert v["version_no"] == 1
    assert v["uploaded"] is False


def test_get_document_backfills_initial_version(client, admin_token):
    r = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "version-backfill-doc", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    r2 = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 200, r2.text
    versions = r2.json()["data"]["versions"]
    assert len(versions) >= 1


def test_delete_last_version_moves_document_to_recycle(client, admin_token):
    r = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "version-delete-doc", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    version_id = r.json()["data"]["versions"][0]["id"]
    dr = client.delete(
        f"/api/v1/documents/{doc_id}/versions/{version_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dr.status_code == 200, dr.text
    body = dr.json()["data"]
    assert body["document_deleted"] is True

    detail = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"].get("deleted_at")
