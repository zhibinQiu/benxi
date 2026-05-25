"""部门管理与系统监控 API 测试。"""

from __future__ import annotations


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_monitor_metrics_ok(client, admin_token):
    r = client.get("/api/v1/monitor/metrics", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "cpu" in data
    assert "memory" in data
    assert "gpus" in data


def test_monitor_audit_logs_ok(client, admin_token):
    r = client.get("/api/v1/monitor/audit-logs?limit=10", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["data"], list)


def test_delete_department_rejects_child(client, admin_token):
    parent = client.post(
        "/api/v1/departments",
        headers=_auth(admin_token),
        json={"name": "测试父部门", "parent_id": None, "sort_order": 0},
    )
    assert parent.status_code == 200, parent.text
    parent_id = parent.json()["data"]["id"]
    child = client.post(
        "/api/v1/departments",
        headers=_auth(admin_token),
        json={"name": "测试子部门", "parent_id": parent_id, "sort_order": 0},
    )
    assert child.status_code == 200, child.text
    r = client.delete(
        f"/api/v1/departments/{parent_id}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 400
    assert "下级" in r.json()["detail"]["message"]


def test_delete_department_ok(client, admin_token):
    created = client.post(
        "/api/v1/departments",
        headers=_auth(admin_token),
        json={"name": "待删除部门", "parent_id": None, "sort_order": 99},
    )
    assert created.status_code == 200, created.text
    dept_id = created.json()["data"]["id"]
    r = client.delete(
        f"/api/v1/departments/{dept_id}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] is True
