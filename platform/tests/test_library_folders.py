"""知识库文件夹 API。"""

from __future__ import annotations

import uuid

from app.database import SessionLocal
from app.models.org import User
from app.services import library_folder_service as lfs
from sqlalchemy import select


def test_can_manage_personal_folders(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get(
        "/api/v1/documents/kb-folders",
        params={"scope": "personal"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["can_manage_folders"] is True
    kinds = {i["kind"] for i in data["items"]}
    assert "uncategorized" in kinds
    assert "shared" in kinds


def test_update_folder_name_and_description(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    name = f"编辑夹-{uuid.uuid4().hex[:8]}"
    cr = client.post(
        "/api/v1/documents/kb-folders",
        json={"name": name, "description": "旧介绍", "scope": "personal"},
        headers=headers,
    )
    assert cr.status_code == 200, cr.text
    folder_id = cr.json()["data"]["id"]

    ur = client.patch(
        f"/api/v1/documents/kb-folders/{folder_id}",
        json={"name": name + "-新", "description": "新介绍"},
        headers=headers,
    )
    assert ur.status_code == 200, ur.text
    body = ur.json()["data"]
    assert body["name"] == name + "-新"
    assert body["description"] == "新介绍"

    client.delete(f"/api/v1/documents/kb-folders/{folder_id}", headers=headers)


def test_create_list_delete_folder(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    name = f"测试夹-{uuid.uuid4().hex[:8]}"
    cr = client.post(
        "/api/v1/documents/kb-folders",
        json={"name": name, "scope": "personal"},
        headers=headers,
    )
    assert cr.status_code == 200, cr.text
    folder_id = cr.json()["data"]["id"]

    lr = client.get(
        "/api/v1/documents/kb-folders",
        params={"scope": "personal"},
        headers=headers,
    )
    names = [i["name"] for i in lr.json()["data"]["items"]]
    assert name in names

    dr = client.delete(
        f"/api/v1/documents/kb-folders/{folder_id}",
        headers=headers,
    )
    assert dr.status_code == 200, dr.text


def test_create_document_in_folder(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    name = f"夹-{uuid.uuid4().hex[:6]}"
    folder = client.post(
        "/api/v1/documents/kb-folders",
        json={"name": name, "scope": "personal"},
        headers=headers,
    ).json()["data"]

    doc = client.post(
        "/api/v1/documents",
        json={
            "title": "文件夹内文档",
            "scope": "personal",
            "folder_id": folder["id"],
        },
        headers=headers,
    )
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["data"]["id"]
    from tests.test_document_versions import _upload_dummy_pdf

    _upload_dummy_pdf(client, doc_id, headers)

    listed = client.get(
        "/api/v1/documents",
        params={
            "scope": "personal",
            "folder_id": folder["id"],
            "page": 1,
            "page_size": 20,
        },
        headers=headers,
    )
    assert listed.status_code == 200
    ids = [i["id"] for i in listed.json()["data"]["items"]]
    assert doc_id in ids


def test_move_document_between_folders(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    a = client.post(
        "/api/v1/documents/kb-folders",
        json={"name": f"源-{uuid.uuid4().hex[:6]}", "scope": "personal"},
        headers=headers,
    ).json()["data"]
    b = client.post(
        "/api/v1/documents/kb-folders",
        json={"name": f"目标-{uuid.uuid4().hex[:6]}", "scope": "personal"},
        headers=headers,
    ).json()["data"]
    doc = client.post(
        "/api/v1/documents",
        json={
            "title": "待移动文档",
            "scope": "personal",
            "folder_id": a["id"],
        },
        headers=headers,
    )
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["data"]["id"]
    from tests.test_document_versions import _upload_dummy_pdf

    _upload_dummy_pdf(client, doc_id, headers)

    moved = client.post(
        f"/api/v1/documents/{doc_id}/move",
        json={"folder_id": b["id"]},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["folder_id"] == b["id"]
    assert moved.json()["data"]["folder_name"] == b["name"]

    to_uncat = client.post(
        f"/api/v1/documents/{doc_id}/move",
        json={"folder_id": None},
        headers=headers,
    )
    assert to_uncat.status_code == 200, to_uncat.text
    assert to_uncat.json()["data"]["folder_id"] is None

    client.delete(f"/api/v1/documents/kb-folders/{a['id']}", headers=headers)
    client.delete(f"/api/v1/documents/kb-folders/{b['id']}", headers=headers)


def test_list_personal_folder_includes_can_delete(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    from tests.test_document_versions import _upload_dummy_pdf

    doc = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "列表删除权限", "scope": "personal"},
    )
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)

    listed = client.get(
        "/api/v1/documents",
        params={"scope": "personal", "uncategorized": True, "page": 1, "page_size": 50},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    row = next(i for i in listed.json()["data"]["items"] if i["id"] == doc_id)
    assert row["can_delete"] is True
    assert row["can_edit"] is True


def test_delete_active_document_purges(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    from tests.test_document_versions import _upload_dummy_pdf

    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "待删除文档", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)

    dr = client.delete(f"/api/v1/documents/{doc_id}/permanent", headers=headers)
    assert dr.status_code == 200, dr.text

    gone = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert gone.status_code == 404


def test_library_tabs_order_and_shared(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/documents/library", headers=headers)
    scopes = [f["scope"] for f in r.json()["data"]["folders"]]
    assert scopes == ["personal", "team", "department", "company", "shared"]
    personal = next(f for f in r.json()["data"]["folders"] if f["scope"] == "personal")
    assert personal.get("can_manage_folders") is True
    shared = next(f for f in r.json()["data"]["folders"] if f["scope"] == "shared")
    assert shared.get("can_create") is False
