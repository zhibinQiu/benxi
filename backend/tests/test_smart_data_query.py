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


def test_smart_data_query_plugin_registered():
    from app.features.registry import get_plugin
    from app.integrations.dify_chat_client import is_dify_configured

    p = get_plugin("smart_data_query")
    assert p is not None
    assert p.title == "智能问数"
    assert p.route == "/system/smart-data-query"
    assert p.enabled is True
    assert isinstance(is_dify_configured(), bool)
