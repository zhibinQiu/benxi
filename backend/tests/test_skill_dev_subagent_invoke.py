"""skill-dev 经 invoke_context_subagent 调研时不应被 Skill 白名单拦截。"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.core.tool_skill_taxonomy import skill_runtime_tools_for_agent
from app.database import SessionLocal, engine
from app.models.org import User
from app.schema_migrate import ensure_agent_profile_schema
from app.services.agent_tools import execute_agent_tool


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_skill_dev_runtime_includes_context_subagent():
    names = skill_runtime_tools_for_agent("skill-dev")
    assert "invoke_context_subagent" in names


def test_isolated_subagent_invoke_skill_bypasses_allowed_skills():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = _admin_user(db)
        loop_state = {
            "agent_id": "skill-dev",
            "allowed_skill_names": {"skill-development"},
            "isolated_subagent": True,
        }
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="invoke_skill",
                arguments={
                    "skill_name": "web-search",
                    "action": "search",
                    "params": {"query": "全国碳市场最新价格"},
                },
                loop_state=loop_state,
            )
        )
        payload = json.loads(raw)
        assert "当前智能体未绑定 Skill" not in str(payload.get("summary") or "")
    finally:
        db.close()


def test_skill_dev_direct_invoke_skill_gets_helpful_error():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = _admin_user(db)
        loop_state = {
            "agent_id": "skill-dev",
            "allowed_skill_names": {"skill-development"},
        }
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="invoke_skill",
                arguments={
                    "skill_name": "web-search",
                    "action": "search",
                    "params": {"query": "test"},
                },
                loop_state=loop_state,
            )
        )
        payload = json.loads(raw)
        assert payload.get("ok") is False
        summary = str(payload.get("summary") or "")
        assert "invoke_context_subagent" in summary
        assert "web-search" in summary
    finally:
        db.close()
