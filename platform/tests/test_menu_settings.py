"""菜单可见性与资源配置权限。"""

from __future__ import annotations

import uuid

import pytest

from app.services.menu_settings_service import DEFAULT_MENU_VISIBILITY


def test_member_menu_visibility_defaults(client, admin_token):
    r = client.get(
        "/api/v1/system/menus",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    keys = set(r.json()["data"]["keys"])
    assert keys == set(DEFAULT_MENU_VISIBILITY.keys())


def test_admin_can_update_menu_visibility(client, admin_token):
    r = client.put(
        "/api/v1/admin/menu-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"menu_visibility": {"ai-home": "all", "documents": "admin"}},
    )
    assert r.status_code == 200, r.text
    visibility = r.json()["data"]["menu_visibility"]
    assert visibility["documents"] == "admin"
    assert visibility["ai-home"] == "all"


def _register_member_token(client) -> str | None:
    phone = f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": f"{phone}@example.com",
            "display_name": "菜单测试用户",
            "password": "secret12",
        },
    )
    if reg.status_code == 403:
        return None
    assert reg.status_code == 200, reg.text
    return reg.json()["data"]["access_token"]


def test_member_sees_filtered_menus(client, admin_token):
    member_token = _register_member_token(client)
    if not member_token:
        pytest.skip("公开注册未开启")

    client.put(
        "/api/v1/admin/menu-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"menu_visibility": {"documents": "admin", "ai-home": "all"}},
    )

    r = client.get(
        "/api/v1/system/menus",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 200, r.text
    keys = r.json()["data"]["keys"]
    assert "documents" not in keys
    assert "ai-home" in keys


def test_hidden_menu_not_visible_to_admin(client, admin_token):
    client.put(
        "/api/v1/admin/menu-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"menu_visibility": {"documents": "hidden", "ai-home": "all"}},
    )

    r = client.get(
        "/api/v1/system/menus",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    keys = r.json()["data"]["keys"]
    assert "documents" not in keys
    assert "ai-home" in keys


def test_member_cannot_update_menu_settings(client):
    member_token = _register_member_token(client)
    if not member_token:
        pytest.skip("公开注册未开启")

    r = client.put(
        "/api/v1/admin/menu-settings",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"menu_visibility": {"documents": "hidden"}},
    )
    assert r.status_code == 403, r.text


def test_member_cannot_update_model_settings(client):
    member_token = _register_member_token(client)
    if not member_token:
        pytest.skip("公开注册未开启")

    title = f"成员配置标题{uuid.uuid4().hex[:6]}"
    r = client.put(
        "/api/v1/admin/model-settings",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"frontend_app_title": title},
    )
    assert r.status_code == 403, r.text
