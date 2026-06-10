"""知识检索文档树 API。"""

from __future__ import annotations


def test_knowledge_scope_tree_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/knowledge/scope-tree", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "items" in body
    assert "knowflow_enabled" in body
