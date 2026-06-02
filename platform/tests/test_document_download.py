"""文档代理下载（不依赖浏览器访问 MinIO）。"""

from __future__ import annotations

import httpx

from tests.test_document_versions import _upload_dummy_pdf


def test_download_document_file(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "download-test", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)

    res = client.get(f"/api/v1/documents/{doc_id}/file", headers=headers)
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF")
    assert "attachment" in (res.headers.get("content-disposition") or "").lower()
