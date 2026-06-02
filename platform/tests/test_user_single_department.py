"""用户仅能归属一个部门。"""

from __future__ import annotations

import uuid

import pytest


def test_create_user_rejects_multiple_departments(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    depts = client.get("/api/v1/departments", headers=headers).json()["data"]
    if len(depts) < 2:
        pytest.skip("需要至少两个部门")
    uname = f"multi_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": uname,
            "password": "Test1234!",
            "department_ids": [depts[0]["id"], depts[1]["id"]],
            "role_ids": [],
        },
    )
    assert r.status_code == 422, r.text
