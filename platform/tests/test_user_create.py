"""管理员创建用户。"""

from __future__ import annotations

import uuid


def test_create_user_via_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    phone = f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"
    display_name = f"新建{uuid.uuid4().hex[:4]}"
    create = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "phone": phone,
            "display_name": display_name,
            "password": "Test1234!",
            "email": f"{phone}@test.local",
            "status": "disabled",
            "department_ids": [],
            "role_ids": [],
        },
    )
    assert create.status_code == 200, create.text
    body = create.json()["data"]
    assert body["phone"] == phone
    assert body["display_name"] == display_name
    assert body["status"] == "disabled"
    assert body["role_names"]

    listed = client.get("/api/v1/users", headers=headers).json()["data"]
    assert any(u["id"] == body["id"] for u in listed)

    deleted = client.delete(f"/api/v1/users/{body['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
