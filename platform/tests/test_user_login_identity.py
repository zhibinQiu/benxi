"""手机号 / 用户名登录与邮箱唯一性。"""

from __future__ import annotations

import uuid

import pytest

from app.core.user_identity import normalize_email


def _random_phone() -> str:
    return f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"


def test_login_by_username(client):
    phone = _random_phone()
    uname = f"user_{uuid.uuid4().hex[:6]}"
    email = f"{uname}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": email,
            "display_name": "测试用户",
            "username": uname,
            "password": "secret12",
        },
    )
    if r.status_code == 403:
        pytest.skip("公开注册未开启")
    assert r.status_code == 200, r.text

    login = client.post(
        "/api/v1/auth/login",
        json={"account": uname.upper(), "password": "secret12"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["data"]["username"] == uname


def test_register_requires_unique_email(client):
    phone1 = _random_phone()
    phone2 = _random_phone()
    tag = uuid.uuid4().hex[:6]
    email = f"dup_{tag}@example.com"
    first = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone1,
            "email": email,
            "display_name": f"用户甲{tag}",
            "password": "secret12",
        },
    )
    if first.status_code == 403:
        pytest.skip("公开注册未开启")
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone2,
            "email": email,
            "display_name": f"用户乙{tag}",
            "password": "secret12",
        },
    )
    assert second.status_code == 400


def test_normalize_email_lowercase():
    assert normalize_email("User@Example.COM") == "user@example.com"
