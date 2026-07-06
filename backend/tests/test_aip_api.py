"""AIP 发现服务单元测试。"""

from __future__ import annotations

from app.database import SessionLocal
from app.services.aip_registry_service import discover_agents, get_agent_by_aid
from app.core.aip.aid import build_agent_aid


def test_discover_agents_returns_builtin():
    db = SessionLocal()
    try:
        out = discover_agents(db, q="检索")
        assert out.total >= 1
        aids = {item.aid for item in out.items}
        assert build_agent_aid("research") in aids
    finally:
        db.close()


def test_discover_by_capability():
    db = SessionLocal()
    try:
        out = discover_agents(db, capability="cap:platform")
        assert any(item.aid.endswith("agent:platform-001") for item in out.items)
    finally:
        db.close()


def test_get_agent_by_aid():
    db = SessionLocal()
    try:
        aid = build_agent_aid("orchestrator")
        detail = get_agent_by_aid(db, aid)
        assert detail.aid == aid
        assert detail.name
    finally:
        db.close()
