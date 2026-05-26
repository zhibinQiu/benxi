"""智能问数对话 API。"""

from __future__ import annotations


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_smart_data_query_meta(client, admin_token):
    r = client.get("/api/v1/smart-data-query/meta", headers=_auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "available" in data
    assert data["provider"] == "smart_data_query_v2"


def test_smart_data_query_meta_requires_auth(client):
    r = client.get("/api/v1/smart-data-query/meta")
    assert r.status_code == 401
