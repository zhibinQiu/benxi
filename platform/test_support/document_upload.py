"""文档上传测试辅助。"""

from __future__ import annotations


def upload_dummy_pdf(client, doc_id: str, headers: dict) -> None:
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
