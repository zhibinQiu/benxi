"""文档版本：须已上传文件，无空占位版本。"""

from __future__ import annotations


def _upload_dummy_pdf(client, doc_id: str, headers: dict) -> None:
    prep = client.post(
        f"/api/v1/documents/{doc_id}/upload/prepare",
        params={"file_name": "test.pdf", "mime_type": "application/pdf"},
        headers=headers,
    )
    assert prep.status_code == 200, prep.text
    data = prep.json()["data"]
    body = b"%PDF-1.4\n% test content\n"
    put = client.put(
        data["upload_url"],
        headers={**headers, "Content-Type": "application/pdf"},
        content=body,
    )
    assert put.status_code in (200, 204), put.text
    complete = client.post(
        f"/api/v1/documents/{doc_id}/upload/complete",
        headers=headers,
        json={"version_id": data["version_id"], "file_size": len(body)},
    )
    assert complete.status_code == 200, complete.text


def test_create_document_without_file_has_no_versions(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "no-file-yet", "scope": "personal"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["versions"] == []


def test_create_document_with_upload(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "with-file", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)
    r2 = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert r2.status_code == 200, r2.text
    versions = r2.json()["data"]["versions"]
    assert len(versions) >= 1
    assert versions[0]["uploaded"] is True


def test_upload_new_version_format_mismatch(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "fmt-check", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)
    prep = client.post(
        f"/api/v1/documents/{doc_id}/upload/prepare",
        params={"file_name": "v2.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        headers=headers,
    )
    assert prep.status_code == 400, prep.text


def test_upload_new_version_with_change_description(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "change-desc", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)
    prep = client.post(
        f"/api/v1/documents/{doc_id}/upload/prepare",
        params={"file_name": "v2.pdf", "mime_type": "application/pdf"},
        headers=headers,
    )
    assert prep.status_code == 200, prep.text
    data = prep.json()["data"]
    body = b"%PDF-1.4\n% v2 content\n"
    put = client.put(
        data["upload_url"],
        headers={**headers, "Content-Type": "application/pdf"},
        content=body,
    )
    assert put.status_code in (200, 204), put.text
    complete = client.post(
        f"/api/v1/documents/{doc_id}/upload/complete",
        headers=headers,
        json={
            "version_id": data["version_id"],
            "file_size": len(body),
            "change_description": "更新了第二章内容",
        },
    )
    assert complete.status_code == 200, complete.text
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    versions = detail.json()["data"]["versions"]
    latest = max(versions, key=lambda x: x["version_no"])
    assert latest["change_description"] == "更新了第二章内容"


def test_upload_complete_returns_string_knowledge_job_id(client, admin_token, monkeypatch):
    import uuid

    job_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.knowledge.enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.KnowledgeGateway.schedule_sync_after_ingest",
        staticmethod(lambda *args, **kwargs: job_id),
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "job-id-str", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    prep = client.post(
        f"/api/v1/documents/{doc_id}/upload/prepare",
        params={"file_name": "test.pdf", "mime_type": "application/pdf"},
        headers=headers,
    )
    assert prep.status_code == 200, prep.text
    data = prep.json()["data"]
    body = b"%PDF-1.4\n% test content\n"
    put = client.put(
        data["upload_url"],
        headers={**headers, "Content-Type": "application/pdf"},
        content=body,
    )
    assert put.status_code in (200, 204), put.text
    complete = client.post(
        f"/api/v1/documents/{doc_id}/upload/complete",
        headers=headers,
        json={"version_id": data["version_id"], "file_size": len(body)},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["data"]["knowledge_job_id"] == str(job_id)


def test_delete_last_version_moves_document_to_recycle(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "version-delete-doc", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    version_id = detail.json()["data"]["versions"][0]["id"]
    dr = client.delete(
        f"/api/v1/documents/{doc_id}/versions/{version_id}",
        headers=headers,
    )
    assert dr.status_code == 200, dr.text
    body = dr.json()["data"]
    assert body["document_deleted"] is True

    detail2 = client.get(
        f"/api/v1/documents/{doc_id}",
        headers=headers,
    )
    assert detail2.status_code == 200
    assert detail2.json()["data"].get("deleted_at")
