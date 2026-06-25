"""部门与用户名称互斥、部门归属校验。"""

from __future__ import annotations

import uuid


def _phone() -> str:
    return f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"


def test_create_department_rejects_user_name(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    uname = f"dept_user_{uuid.uuid4().hex[:8]}"
    phone = _phone()
    user = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "phone": phone,
            "email": f"{phone}@test.local",
            "display_name": uname,
            "password": "Test1234!",
            "department_ids": [],
            "role_ids": [],
        },
    )
    assert user.status_code == 200, user.text

    r = client.post(
        "/api/v1/departments",
        headers=headers,
        json={"name": uname, "parent_id": None},
    )
    assert r.status_code == 400, r.text
    assert "用户姓名" in r.json()["message"]


def test_create_user_rejects_department_name(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    dept = client.post(
        "/api/v1/departments",
        headers=headers,
        json={"name": f"唯一部门_{uuid.uuid4().hex[:6]}", "parent_id": None},
    )
    assert dept.status_code == 200, dept.text
    dept_name = dept.json()["data"]["name"]
    phone = _phone()

    r = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "phone": phone,
            "email": f"{phone}@test.local",
            "display_name": dept_name,
            "password": "Test1234!",
            "department_ids": [],
            "role_ids": [],
        },
    )
    assert r.status_code == 400, r.text
    assert "部门名称" in r.json()["message"]


def test_update_user_rejects_missing_department(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    phone = _phone()
    uname = f"dept_bind_{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "phone": phone,
            "email": f"{phone}@test.local",
            "display_name": uname,
            "password": "Test1234!",
            "department_ids": [],
            "role_ids": [],
        },
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["data"]["id"]

    r = client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"department_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 400, r.text
    assert "部门不存在" in r.json()["message"]

