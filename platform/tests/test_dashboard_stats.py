"""运行大屏统计 API 测试。"""

from __future__ import annotations


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_stats_ok(client, admin_token):
    r = client.get("/api/v1/system/dashboard-stats", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "documents_total" in data
    assert "documents_indexed" in data
    assert "features_total" in data
    assert "features_pending" in data
    assert "users_registered" in data
    assert "users_online" in data
    assert data["features_total"] >= data["features_pending"] >= 0
    assert data["documents_total"] >= data["documents_indexed"] >= 0
    assert data["users_registered"] >= data["users_online"] >= 1


def test_dashboard_stats_requires_auth(client):
    r = client.get("/api/v1/system/dashboard-stats")
    assert r.status_code == 401
