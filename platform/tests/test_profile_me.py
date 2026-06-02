"""当前用户个人信息维护。"""

from __future__ import annotations

import uuid

import pytest


def _random_phone() -> str:
    return f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"


def _register_user(client):
    phone = _random_phone()
    display_name = f"用户{uuid.uuid4().hex[:4]}"
    r = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": f"{phone}@example.com",
            "display_name": display_name,
            "password": "secret12",
        },
    )
    if r.status_code == 403:
        pytest.skip("公开注册未开启（ALLOW_PUBLIC_REGISTER=false）")
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]
    return token, phone, display_name


def test_update_me_profile(client):
    token, phone, display_name = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    new_name = f"新名{display_name[-2:]}"
    new_email = f"new_{phone}@example.com"

    r = client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={
            "display_name": new_name,
            "email": new_email,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["display_name"] == new_name
    assert body["email"] == new_email
    assert "role_names" in body

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["display_name"] == new_name
