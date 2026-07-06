"""路由目录 API 测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_routing_catalog_endpoints_readonly():
    client = TestClient(app)
    # 需登录与权限；此处仅验证路由注册（未授权应 401/403 而非 404）
    skills_resp = client.get("/api/v1/admin/agent-skills/routing/skills.md")
    agents_resp = client.get("/api/v1/admin/agent-skills/routing/agents.md")
    assert skills_resp.status_code in (401, 403, 200)
    assert agents_resp.status_code in (401, 403, 200)
    assert skills_resp.status_code != 404
    assert agents_resp.status_code != 404
