"""问题登记 API。"""

from __future__ import annotations

import uuid


def _register_member(client) -> str:
    phone = f"138{int(uuid.uuid4().hex[:8], 16) % 100000000:08d}"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": f"{phone}@example.com",
            "display_name": "问题登记测试",
            "password": "secret12",
        },
    )
    assert reg.status_code == 200, reg.text
    return reg.json()["data"]["access_token"]


def test_member_can_create_and_list_issue(client, admin_token):
    member_token = _register_member(client)
    create = client.post(
        "/api/v1/issue-reports",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"description": "登录后文档列表加载缓慢"},
    )
    assert create.status_code == 200, create.text
    body = create.json()["data"]
    assert body["status"] == "open"
    assert body["description"] == "登录后文档列表加载缓慢"
    assert body["reporter_name"] == "问题登记测试"

    listed = client.get(
        "/api/v1/issue-reports",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert any(r["id"] == body["id"] for r in rows)

    forbidden = client.patch(
        f"/api/v1/issue-reports/{body['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"status": "fixed"},
    )
    assert forbidden.status_code == 403, forbidden.text

    fixed = client.patch(
        f"/api/v1/issue-reports/{body['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "fixed"},
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["data"]["status"] == "fixed"
    assert fixed.json()["data"]["fixed_by_name"]

    filtered = client.get(
        "/api/v1/issue-reports?status=fixed",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert filtered.status_code == 200, filtered.text
    assert all(r["status"] == "fixed" for r in filtered.json()["data"])

    member_delete = client.delete(
        f"/api/v1/issue-reports/{body['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_delete.status_code == 403, member_delete.text

    deleted = client.delete(
        f"/api/v1/issue-reports/{body['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] is True

    listed_after = client.get(
        "/api/v1/issue-reports",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert listed_after.status_code == 200, listed_after.text
    assert not any(r["id"] == body["id"] for r in listed_after.json()["data"])
