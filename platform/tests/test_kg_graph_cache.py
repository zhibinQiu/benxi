"""本体图谱子图缓存。"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.platform_cache import cache_get_json, kg_graph_cache_key
from app.database import SessionLocal
from app.models.org import User


def test_kg_graph_served_from_cache(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta", headers=headers)
    assert meta.status_code == 200
    type_id = meta.json()["data"]["entity_types"][0]["id"]

    create = client.post(
        "/api/v1/kg/entities",
        headers=headers,
        json={"type_id": type_id, "name": "缓存测试实体", "description": ""},
    )
    assert create.status_code == 200
    entity_id = create.json()["data"]["id"]

    calls = {"count": 0}
    original = None

    def counting_build(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    from app.services import kg_service

    original = kg_service._build_graph
    with patch.object(kg_service, "_build_graph", side_effect=counting_build):
        url = f"/api/v1/kg/graph?focus_entity_id={entity_id}&depth=1"
        first = client.get(url, headers=headers)
        second = client.get(url, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1

    client.delete(f"/api/v1/kg/entities/{entity_id}", headers=headers)


def test_kg_graph_cache_invalidated_on_entity_delete(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta", headers=headers)
    type_id = meta.json()["data"]["entity_types"][0]["id"]

    create = client.post(
        "/api/v1/kg/entities",
        headers=headers,
        json={"type_id": type_id, "name": "缓存失效测试", "description": ""},
    )
    entity_id = create.json()["data"]["id"]
    url = f"/api/v1/kg/graph?focus_entity_id={entity_id}&depth=1"

    client.get(url, headers=headers)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        cache_key = kg_graph_cache_key(str(user.id), entity_id, 1)
    finally:
        db.close()

    assert cache_get_json(cache_key, ttl=120) is not None

    client.delete(f"/api/v1/kg/entities/{entity_id}", headers=headers)
    assert cache_get_json(cache_key, ttl=120) is None
