"""系统智能体注册表与配置 API 测试。"""

from __future__ import annotations

from app.database import engine
from app.schema_migrate import ensure_agent_profile_schema
from app.services.agent_runtime_service import mark_agent_idle, mark_agent_running


def test_list_builtin_agents(client, admin_token):
    ensure_agent_profile_schema(engine)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/admin/agent-skills/agents", headers=headers)
    assert r.status_code == 200, r.text
    agents = r.json()["data"]
    ids = [item["id"] for item in agents]
    assert "orchestrator" in ids
    assert "platform" in ids
    assert "research" in ids
    assert ids.index("orchestrator") < ids.index("platform")


def test_patch_agent_skills(client, admin_token):
    ensure_agent_profile_schema(engine)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.patch(
        "/api/v1/admin/agent-skills/agents/research",
        headers=headers,
        json={"skill_names": ["web-search", "knowledge-search"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["skill_names"] == ["web-search", "knowledge-search"]

    r2 = client.get("/api/v1/admin/agent-skills/agents/research", headers=headers)
    assert r2.json()["data"]["skill_names"] == ["web-search", "knowledge-search"]


def test_orchestrator_skills_not_configurable(client, admin_token):
    ensure_agent_profile_schema(engine)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.patch(
        "/api/v1/admin/agent-skills/agents/orchestrator",
        headers=headers,
        json={"skill_names": ["web-search"]},
    )
    assert r.status_code == 400, r.text


def test_runtime_status_exposed(client, admin_token):
    ensure_agent_profile_schema(engine)
    headers = {"Authorization": f"Bearer {admin_token}"}
    mark_agent_running("platform", "conv-1")
    try:
        r = client.get("/api/v1/admin/agent-skills/agents/platform", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "running"
        assert data["active_conversations"] == 1
        assert "AGENT.md" in data["files"]
    finally:
        mark_agent_idle("platform", "conv-1")


def test_agent_config_file_read_and_update(client, admin_token):
    ensure_agent_profile_schema(engine)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get(
        "/api/v1/admin/agent-skills/agents/research/files/AGENT.md",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    original = r.json()["data"]["text"]
    assert "id: research" in original
    assert "description:" in original

    updated_md = original.replace(
        "description:",
        "description: 测试路由描述 — 用户要查资料时使用。",
        1,
    )
    r2 = client.put(
        "/api/v1/admin/agent-skills/agents/research/files/AGENT.md",
        headers=headers,
        json={"content": updated_md},
    )
    assert r2.status_code == 200, r2.text

    r3 = client.get("/api/v1/admin/agent-skills/agents/research", headers=headers)
    assert "测试路由描述" in r3.json()["data"]["description"]
