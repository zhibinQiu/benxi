"""本体图谱实体批量操作与清空。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models.kg import KgEntity, KgRelation
from app.models.org import User
from app.services.kg.entity_commands import batch_delete_entities, clear_user_graph
from app.services.kg_service import create_entity, ensure_ontology_defaults
from app.schemas.kg import KgEntityIn


def test_batch_delete_entities_by_ids(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta?sync_system=true", headers=headers)
    type_id = meta.json()["data"]["entity_types"][0]["id"]

    created_ids = []
    for name in ("批量删A", "批量删B", "保留C"):
        res = client.post(
            "/api/v1/kg/entities",
            headers=headers,
            json={"type_id": type_id, "name": name, "description": ""},
        )
        created_ids.append(res.json()["data"]["id"])

    delete = client.post(
        "/api/v1/kg/entities/batch-delete",
        headers=headers,
        json={"entity_ids": created_ids[:2]},
    )
    assert delete.status_code == 200
    assert delete.json()["data"]["deleted_count"] == 2

    entities = client.get("/api/v1/kg/entities", headers=headers)
    names = {e["name"] for e in entities.json()["data"]}
    assert "批量删A" not in names
    assert "批量删B" not in names
    assert "保留C" in names

    client.post(
        "/api/v1/kg/entities/batch-delete",
        headers=headers,
        json={"entity_ids": [created_ids[2]]},
    )


def test_batch_delete_entities_by_search(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta?sync_system=true", headers=headers)
    type_id = meta.json()["data"]["entity_types"][0]["id"]

    for name in ("搜索删甲", "搜索删乙", "其它实体"):
        client.post(
            "/api/v1/kg/entities",
            headers=headers,
            json={"type_id": type_id, "name": name, "description": ""},
        )

    delete = client.post(
        "/api/v1/kg/entities/batch-delete",
        headers=headers,
        json={"q": "搜索删"},
    )
    assert delete.status_code == 200
    assert delete.json()["data"]["deleted_count"] == 2


def test_clear_user_graph(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta?sync_system=true", headers=headers)
    type_id = meta.json()["data"]["entity_types"][0]["id"]
    client.post(
        "/api/v1/kg/entities",
        headers=headers,
        json={"type_id": type_id, "name": "待清空实体", "description": ""},
    )

    cleared = client.post("/api/v1/kg/graph/clear", headers=headers)
    assert cleared.status_code == 200
    data = cleared.json()["data"]
    assert data["deleted_entities"] >= 1

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        remaining = db.scalar(
            select(KgEntity.id).where(KgEntity.owner_id == user.id).limit(1)
        )
        assert remaining is None
    finally:
        db.close()


def test_entity_commands_unit():
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        ensure_ontology_defaults(db)
        db.commit()
        from app.models.kg import KgEntityType

        et = db.scalar(select(KgEntityType).limit(1))
        assert et is not None
        a = create_entity(
            db,
            user,
            KgEntityIn(type_id=et.id, name="单元测试实体A", description=""),
        )
        b = create_entity(
            db,
            user,
            KgEntityIn(type_id=et.id, name="单元测试实体B", description=""),
        )
        count = batch_delete_entities(db, user, entity_ids=[a.id])
        assert count == 1
        clear_stats = clear_user_graph(db, user)
        assert clear_stats["deleted_entities"] >= 1
        rel_left = db.scalar(
            select(KgRelation.id).where(KgRelation.owner_id == user.id).limit(1)
        )
        assert rel_left is None
    finally:
        db.close()
