"""用户删除级联。"""

from __future__ import annotations

import uuid


def test_delete_user_via_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    users = client.get("/api/v1/users", headers=headers).json()["data"]
    template = next((u for u in users if u["username"] == "admin"), users[0])

    uname = f"todel_{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": uname,
            "password": "Test1234!",
            "email": f"{uname}@test.local",
            "department_ids": template.get("department_ids") or [],
            "role_ids": template.get("role_ids") or [],
        },
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] is True

    again = client.get("/api/v1/users", headers=headers).json()["data"]
    assert not any(u["id"] == user_id for u in again)
