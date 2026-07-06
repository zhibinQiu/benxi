"""本体图谱 — 插件注册与基础 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.database import SessionLocal
from app.models.org import User
from app.services.ai_chat_service import _build_chat_messages
from app.services.skill_chat_service import resolve_kg_context_via_skill_sync as resolve_kg_context_via_skill
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
    assert len(data["entity_types"]) >= 9
    assert len(data["relation_types"]) >= 10

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
    client.get("/api/v1/kg/meta?sync_system=true", headers=headers)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None

        matches = match_entities_in_question(
            db, user, "全国碳市场管理办法约束哪些指标？"
        )
        names = [ent.name for ent, _ in matches]
        assert "全国碳市场管理办法" in names

        ctx = retrieve_kg_context_for_question(db, user, "系统管理员负责哪些减排项目？")
        assert ctx is not None
        assert ctx.entity_count >= 3
        assert ctx.relation_count >= 1
        assert any("减排路径规划" in c["title"] for c in ctx.citations)
        assert "负责" in ctx.context_text

        empty = retrieve_kg_context_for_question(db, user, "今天天气怎么样")
        assert empty is None
    finally:
        db.close()


def test_ai_home_resolves_kg_context(client: TestClient, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta?sync_system=true", headers=headers)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None

        kg = resolve_kg_context_via_skill(
            db, user, "全国碳市场管理办法与范围一排放量是什么关系？"
        )
        assert kg is not None
        messages = _build_chat_messages(
            message="全国碳市场管理办法与范围一排放量是什么关系？",
            history=[],
            retrieval_context=kg.context_text or "",
        )
        joined = "\n".join(m.get("content") or "" for m in messages)
        assert "全国碳市场管理办法" in joined
        assert "范围一排放量" in joined
    finally:
        db.close()


def test_merge_kg_qa_into_context_offsets_citations():
    doc_citations = [{"index": 1, "title": "doc", "source": "knowflow"}]
    from app.services.kg_service import KgQaContext

    merged_ctx, merged_cites = merge_kg_qa_into_context(
        "[1]\n文档片段",
        doc_citations,
        KgQaContext(
            context_text="【本体图谱实体与关系】\n[1] 法规 · 测试",
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
    assert "本体图谱" in merged_ctx
    assert merged_ctx.index("本体图谱") < merged_ctx.index("文档片段")
    assert merged_cites[0]["index"] == 1
    assert merged_cites[0]["source"] == "kg"
    assert merged_cites[1]["index"] == 2
    assert merged_cites[1]["source"] == "knowflow"


def test_kg_graph_focus_isolated_entity(client: TestClient, admin_token: str):
    """无关系的孤立实体也应出现在子图中。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta", headers=headers)
    assert meta.status_code == 200
    type_id = meta.json()["data"]["entity_types"][0]["id"]

    create = client.post(
        "/api/v1/kg/entities",
        headers=headers,
        json={"type_id": type_id, "name": "孤立测试实体", "description": ""},
    )
    assert create.status_code == 200
    entity_id = create.json()["data"]["id"]

    graph = client.get(
        f"/api/v1/kg/graph?focus_entity_id={entity_id}&depth=1",
        headers=headers,
    )
    assert graph.status_code == 200
    nodes = graph.json()["data"]["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == entity_id

    client.delete(f"/api/v1/kg/entities/{entity_id}", headers=headers)


def test_kg_meta_syncs_platform_org(client: TestClient, admin_token: str):
    """加载 meta 时将平台用户/部门同步为图谱实体。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/kg/meta?sync_system=true", headers=headers)
    assert res.status_code == 200

    entities = client.get("/api/v1/kg/entities", headers=headers)
    assert entities.status_code == 200
    rows = entities.json()["data"]
    orgs = [e for e in rows if e["type_code"] == "org"]
    persons = [e for e in rows if e["type_code"] == "person"]
    assert len(persons) >= 1
    assert any(
        (e.get("properties") or {}).get("platform_user_id")
        for e in persons
    )
    platform_orgs = [
        e for e in orgs if (e.get("properties") or {}).get("platform_department_id")
    ]
    for org in platform_orgs:
        assert (org.get("properties") or {}).get("platform_department_id")


def test_kg_meta_syncs_platform_agents(client: TestClient, admin_token: str):
    """加载 meta 时将平台智能体、工具、技能同步为图谱实体与关系。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/kg/meta?sync_system=true", headers=headers)
    assert res.status_code == 200

    entities = client.get("/api/v1/kg/entities", headers=headers)
    assert entities.status_code == 200
    rows = entities.json()["data"]
    agents = [e for e in rows if e["type_code"] == "agent"]
    tools = [e for e in rows if e["type_code"] == "tool"]
    skills = [e for e in rows if e["type_code"] == "skill"]
    assert len(agents) >= 5
    assert len(tools) >= 5
    assert len(skills) >= 3
    assert any(e["name"] == "检索研究" for e in agents)
    assert any((e.get("properties") or {}).get("platform_agent_id") == "research" for e in agents)
    assert any(e["name"] == "kg_query" for e in tools)
    assert any((e.get("properties") or {}).get("slug") == "knowledge-research" for e in skills)

    relations = client.get("/api/v1/kg/relations", headers=headers)
    assert relations.status_code == 200
    rel_rows = relations.json()["data"]
    rel_type_codes = {r["relation_type_code"] for r in rel_rows}
    assert "has_tool" in rel_type_codes
    assert "has_skill" in rel_type_codes
    assert "orchestrates" in rel_type_codes


def test_kg_list_platform_users_question():
    """「有哪些用户」类问题应返回已同步的平台人员/组织实体。"""
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        ctx = retrieve_kg_context_for_question(db, user, "系统中有哪些用户")
        assert ctx is not None
        assert ctx.entity_count >= 1
        assert "人员" in (ctx.context_text or "") or "组织" in (ctx.context_text or "")
    finally:
        db.close()
