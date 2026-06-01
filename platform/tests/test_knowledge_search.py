"""知识搜索 API。"""

from __future__ import annotations

def test_knowledge_search_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/rag/search",
        headers=headers,
        json={"query": "测试", "limit": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["query"] == "测试"
    assert "hits" in body
    assert body["search_mode"] in ("knowflow", "local")
