"""本体图谱 — 插件注册与基础 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.database import SessionLocal
from app.models.org import User
from app.services.ai_chat_service import _build_chat_messages, _resolve_kg_context
from app.services.kg_service import (
    match_entities_in_question,
    merge_kg_qa_into_context,
    retrieve_kg_context_for_question,
)


def test_kg_palantir_plugin_registered():
    ensure_plugins_loaded()
    plugin = get_plugin("kg_palantir")
    assert plugin is not None
    assert plugin.route == "/system/kg-palantir"
    assert plugin.permission_code == "feature.kg_palantir"
    assert plugin.category == "tools"
    assert plugin.enabled is True


def test_kg_meta_and_crud(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/kg/meta", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["entity_total"] >= 1
    assert len(data["entity_types"]) >= 6
    assert len(data["relation_types"]) >= 6

    types = data["entity_types"]
    type_id = types[0]["id"]
    create = client.post(
        "/api/v1/kg/entities",
        headers=headers,
        json={"type_id": type_id, "name": "测试实体", "description": "demo"},
    )
    assert create.status_code == 200
    entity_id = create.json()["data"]["id"]

    graph = client.get(
        f"/api/v1/kg/graph?focus_entity_id={entity_id}",
        headers=headers,
    )
    assert graph.status_code == 200
    assert any(n["id"] == entity_id for n in graph.json()["data"]["nodes"])

    delete = client.delete(f"/api/v1/kg/entities/{entity_id}", headers=headers)
    assert delete.status_code == 200


def test_kg_question_entity_match_and_context(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None

        matches = match_entities_in_question(
            db, user, "全国碳市场管理办法约束哪些指标？"
        )
        names = [ent.name for ent, _ in matches]
        assert "全国碳市场管理办法" in names

        ctx = retrieve_kg_context_for_question(db, user, "张三负责哪些减排项目？")
        assert ctx is not None
        assert ctx.entity_count >= 3
        assert ctx.relation_count >= 1
        assert any("张三" in c["title"] for c in ctx.citations)
        assert "负责" in ctx.context_text

        empty = retrieve_kg_context_for_question(db, user, "今天天气怎么样")
        assert empty is None
    finally:
        db.close()


def test_ai_home_resolves_kg_context(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None

        kg = _resolve_kg_context(
            db, user, "全国碳市场管理办法与范围一排放量是什么关系？"
        )
        assert kg is not None
        messages = _build_chat_messages(
            message="全国碳市场管理办法与范围一排放量是什么关系？",
            history=[],
            retrieval_context=kg.context_text or "",
        )
        system = messages[0]["content"]
        assert "知识图谱" in system
        assert "全国碳市场管理办法" in system
        assert "范围一排放量" in system
    finally:
        db.close()


def test_merge_kg_qa_into_context_offsets_citations():
    doc_citations = [{"index": 1, "title": "doc", "source": "knowflow"}]
    from app.services.kg_service import KgQaContext

    merged_ctx, merged_cites = merge_kg_qa_into_context(
        "[1]\n文档片段",
        doc_citations,
        KgQaContext(
            context_text="【知识图谱实体与关系】\n[1] 法规 · 测试",
            citations=[
                {
                    "index": 1,
                    "title": "法规 · 测试",
                    "snippet": "demo",
                    "source": "kg",
                    "entity_id": "00000000-0000-0000-0000-000000000001",
                }
            ],
        ),
    )
    assert "知识图谱" in merged_ctx
    assert merged_cites[0]["index"] == 1
    assert merged_cites[1]["index"] == 2
    assert merged_cites[1]["source"] == "kg"
