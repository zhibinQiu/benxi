"""知识检索文档树 API。"""

from __future__ import annotations


def test_knowledge_scope_tree_api(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/knowledge/scope-tree", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "items" in body
    assert "knowflow_enabled" in body


def test_knowledge_scope_tree_has_folder_nodes_under_library(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/knowledge/scope-tree", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"] or []
    libraries = [
        lib
        for scope in items
        for lib in (scope.get("children") or [])
        if lib.get("type") == "library"
    ]
    if not libraries:
        return
    lib = libraries[0]
    folders = lib.get("children") or []
    assert folders, "知识库下应包含文件夹节点"
    assert folders[0].get("type") == "folder"
    assert folders[0].get("virtual_folder_id") == "__uncategorized__"
    assert "index_ready_count" in folders[0]
    assert "children" in folders[0]
    assert lib.get("index_ready_count") is not None


def test_knowledge_scope_tree_includes_personal_scope_with_label(client, admin_token):
    from unittest.mock import patch

    from app.services.knowledge_scope_tree_service import invalidate_scope_tree_cache

    invalidate_scope_tree_cache()
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch(
        "app.services.knowledge_scope_tree_service._read_scope_tree_cache",
        return_value=None,
    ):
        r = client.get("/api/v1/knowledge/scope-tree", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"] or []
    scopes = {item.get("scope"): item for item in items}
    assert "personal" in scopes
    assert scopes["personal"]["label"] == "个人级"
    assert scopes["personal"].get("children")
