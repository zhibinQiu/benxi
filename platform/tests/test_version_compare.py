"""单文档版本对比：预计算与按需任务。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.services.version_compare_service import (
    request_version_pair_compare,
    schedule_precompare_for_version,
)


def _upload_version_text(
    client,
    doc_id: str,
    headers: dict,
    *,
    content: str,
    change_description: str = "",
) -> str:
    body = content.encode("utf-8")
    prep = client.post(
        f"/api/v1/documents/{doc_id}/upload/prepare",
        params={"file_name": "v.txt", "mime_type": "text/plain"},
        headers=headers,
    )
    assert prep.status_code == 200, prep.text
    data = prep.json()["data"]
    put = client.put(
        data["upload_url"],
        headers={**headers, "Content-Type": "text/plain"},
        content=body,
    )
    assert put.status_code in (200, 204), put.text
    complete = client.post(
        f"/api/v1/documents/{doc_id}/upload/complete",
        headers=headers,
        json={
            "version_id": data["version_id"],
            "file_size": len(body),
            "change_description": change_description,
        },
    )
    assert complete.status_code == 200, complete.text
    return data["version_id"]


def test_version_compare_precompute_and_on_demand(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "ver-cmp", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    v1_id = _upload_version_text(
        client, doc_id, headers, content="line one\n", change_description="v1"
    )
    v2_id = _upload_version_text(
        client,
        doc_id,
        headers,
        content="line one\nline two changed\n",
        change_description="v2 changed",
    )
    _ = v1_id, v2_id

    v3_id = _upload_version_text(
        client,
        doc_id,
        headers,
        content="line one\nline two changed\nline three\n",
        change_description="v3",
    )
    v4_id = _upload_version_text(
        client,
        doc_id,
        headers,
        content="line one\nline two changed\nline three\nline four\n",
        change_description="v4",
    )
    _ = v3_id, v4_id

    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    versions = sorted(detail.json()["data"]["versions"], key=lambda x: x["version_no"])
    assert len(versions) >= 4
    v_low = versions[0]["id"]
    v_second = versions[1]["id"]
    v_fourth = versions[3]["id"]

    # 等待预计算 V0↔V4（baseline）
    deadline = time.time() + 15
    rel_done = False
    while time.time() < deadline:
        resp = client.get(
            f"/api/v1/compare/documents/{doc_id}/version-compare",
            headers=headers,
            params={"left_version_id": v_low, "right_version_id": v_fourth},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        if body["status"] == "done":
            rel_done = True
            assert body["precomputed"] is True
            assert isinstance(body.get("diff_items"), list)
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error_message") or "precompare failed")
        time.sleep(0.3)
    assert rel_done, "预对比未在时限内完成"

    # Case 2：V2↔V4 无预计算（跨版本），按需异步
    deadline = time.time() + 15
    on_demand_done = False
    while time.time() < deadline:
        resp = client.get(
            f"/api/v1/compare/documents/{doc_id}/version-compare",
            headers=headers,
            params={"left_version_id": v_second, "right_version_id": v_fourth},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        if body["status"] == "done":
            on_demand_done = True
            assert body["precomputed"] is False
            assert body["relation_type"] == "on_demand"
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error_message") or "on_demand compare failed")
        time.sleep(0.3)
    assert on_demand_done, "按需对比未在时限内完成"

    # 按需：若仅两版，v_low↔v_high 即 V0↔V2；测 relations 列表
    rels = client.get(
        f"/api/v1/compare/documents/{doc_id}/version-compare/relations",
        headers=headers,
    )
    assert rels.status_code == 200
    assert len(rels.json()["data"]) >= 1


def test_schedule_precompare_creates_baseline_and_adjacent(admin_token):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.services.documents.crud import (
        complete_upload,
        create_document,
        create_initial_uploaded_version,
        prepare_upload,
        save_upload_blob,
    )

    db = SessionLocal()
    try:
        user = db.scalar(select(User).limit(1))
        if not user:
            pytest.skip("no user")
        doc = create_document(db, user, title="unit-ver-cmp", scope="personal")
        v1 = create_initial_uploaded_version(
            db,
            doc,
            user,
            file_name="a.txt",
            mime_type="text/plain",
            content=b"line one\n",
        )
        version, _url = prepare_upload(
            db, user, doc, file_name="a.txt", mime_type="text/plain"
        )
        save_upload_blob(
            db, user, doc, version, b"line one\nline two\n", content_type="text/plain"
        )
        complete_upload(
            db,
            user,
            doc,
            version,
            file_size=len(b"line one\nline two\n"),
            checksum=None,
        )
        db.refresh(doc)

        with patch(
            "app.services.version_compare_service.enqueue_version_compare"
        ) as mock_enqueue:
            ids = schedule_precompare_for_version(db, doc.id, version.id)
            assert len(ids) == 1
            assert mock_enqueue.call_count == 1

        from app.models.document_version_compare import DocumentVersionCompareRelation

        rels = (
            db.query(DocumentVersionCompareRelation)
            .filter_by(document_id=doc.id)
            .all()
        )
        types = {r.relation_type for r in rels}
        assert "baseline_v0" in types

        rel = rels[0]
        data = request_version_pair_compare(
            db,
            user,
            doc.id,
            rel.from_version_id,
            rel.to_version_id,
            background=False,
        )
        assert data["status"] == "done"
    finally:
        db.close()
