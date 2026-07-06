"""skill-dev 专精运行时工具暴露与 invoke_skill 领域 Skill 调用。"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.core.tool_skill_taxonomy import SKILL_SKILL_DEV, skill_runtime_tools_for_agent
from app.database import SessionLocal, engine
from app.models.org import User
from app.schema_migrate import ensure_agent_profile_schema
from app.services.agent_skill_runtime import build_agent_runtime_tool_specs
from app.services.agent_tools import execute_agent_tool
from app.core.agent_tool_args import validate_tool_arguments


def test_skill_dev_runtime_matches_platform_pattern():
    names = skill_runtime_tools_for_agent("skill-dev")
    assert "invoke_skill" in names
    assert "create_skill" not in names
    assert "invoke_context_subagent" in names


def test_skill_dev_exposes_invoke_skill_not_flat_mgmt_tools():
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        specs = build_agent_runtime_tool_specs(
            db,
            user,
            agent_id="skill-dev",
            allowed_skill_names=[SKILL_SKILL_DEV],
        )
        exposed = {s["function"]["name"] for s in specs}
        assert "invoke_skill" in exposed
        assert "create_skill" not in exposed
        assert "run_skill_script" not in exposed
    finally:
        db.close()


def test_invoke_skill_skill_development_accepts_domain_call_params():
    params, err = validate_tool_arguments(
        "invoke_skill",
        {
            "skill_name": SKILL_SKILL_DEV,
            "action": "call",
            "params": {
                "operation": "create_skill",
                "name": "demo-skill",
                "description": "test",
                "skill_md_body": "# Demo",
            },
        },
    )
    assert err is None
    assert params and params["params"]["operation"] == "create_skill"


def test_flat_create_skill_still_valid_for_handler():
    """领域 handler 内部仍走 execute_agent_tool(create_skill)。"""
    params, err = validate_tool_arguments(
        "create_skill",
        {
            "name": "demo",
            "description": "test",
            "skill_md_body": "# Demo",
        },
    )
    assert err is None
    assert params and params["name"] == "demo"


def test_list_uploaded_skills_alias_via_skill_development():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="invoke_skill",
                arguments={
                    "skill_name": SKILL_SKILL_DEV,
                    "action": "call",
                    "params": {
                        "operation": "list_uploaded_skills",
                        "params": {"limit": 2},
                    },
                },
                loop_state={
                    "agent_id": "skill-dev",
                    "allowed_skill_names": {SKILL_SKILL_DEV},
                },
            )
        )
        payload = json.loads(raw)
        assert payload["ok"] is True
    finally:
        db.close()


def test_has_skill_research_context_accepts_subagent_summaries():
    from app.core.agent_tool_context import has_skill_research_context

    assert has_skill_research_context(
        {"subagent_summaries": [{"summary": "页面含价格字段"}]},
        needs_site_research=True,
    )


def test_invoke_skill_rejects_runtime_tool_as_skill_name():
    params, err = validate_tool_arguments(
        "invoke_skill",
        {
            "skill_name": "create_skill",
            "action": "call",
            "params": {
                "name": "demo",
                "description": "test",
                "skill_md_body": "# Demo",
            },
        },
    )
    assert err is None
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="invoke_skill",
                arguments=params,
                loop_state={
                    "agent_id": "skill-dev",
                    "allowed_skill_names": {SKILL_SKILL_DEV},
                },
            )
        )
        payload = json.loads(raw)
        assert payload["ok"] is False
        summary = str(payload.get("summary") or "")
        assert "create_skill" in summary
        assert "skill-development" in summary
    finally:
        db.close()
