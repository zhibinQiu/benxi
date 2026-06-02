"""公开注册 API。"""

from __future__ import annotations

import uuid

import pytest


def _random_phone() -> str:
    return f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"


def test_register_creates_member_user(client):
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

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()["data"]
    assert body["phone"] == phone
    assert body["display_name"] == display_name
    assert "admin.user" not in (body.get("permissions") or [])


def test_register_rejects_duplicate_phone(client):
    phone = _random_phone()
    display_name = f"dup_{uuid.uuid4().hex[:4]}"
    first = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": f"{phone}@example.com",
            "display_name": display_name,
            "password": "secret12",
        },
    )
    if first.status_code == 403:
        pytest.skip("公开注册未开启（ALLOW_PUBLIC_REGISTER=false）")
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": f"other_{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "另一个名字",
            "password": "secret12",
        },
    )
    assert second.status_code == 400
