"""公开注册 API。"""

from __future__ import annotations

import uuid

import pytest


def test_register_creates_member_user(client):
    uname = f"reg_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "secret12"},
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
    assert body["username"] == uname
    assert "admin.user" not in (body.get("permissions") or [])


def test_register_rejects_duplicate_username(client):
    uname = f"dup_{uuid.uuid4().hex[:8]}"
    first = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "secret12"},
    )
    if first.status_code == 403:
        pytest.skip("公开注册未开启（ALLOW_PUBLIC_REGISTER=false）")
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "secret12"},
    )
    assert second.status_code == 400
