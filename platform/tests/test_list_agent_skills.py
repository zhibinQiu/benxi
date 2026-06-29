"""list_agent_skills 工具与目录白名单根因修复。"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal, engine
from app.models.org import User
from app.schema_migrate import ensure_agent_profile_schema
from app.services.agent_profile_service import resolve_agent_tool_names
from app.services.agent_tools import execute_agent_tool
from app.skills.catalog import build_agent_catalog_prompt


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_orchestrator_does_not_mount_list_agent_skills():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        names = resolve_agent_tool_names(db, "orchestrator")
        assert "list_agent_skills" not in names
    finally:
        db.close()


def test_skill_dev_has_list_agent_skills():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        names = resolve_agent_tool_names(db, "skill-dev")
        assert "list_agent_skills" in names
    finally:
        db.close()


def test_empty_skill_names_whitelist_shows_full_catalog():
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = _admin_user(db)
        text = build_agent_catalog_prompt(db, user=user, skill_names=[])
        assert "### 发展技能" in text or "### 内置" in text
    finally:
        db.close()


def test_list_agent_skills_tool_returns_uploaded_skill():
    ensure_agent_profile_schema(engine)
    from app.services.agent_skill_service import upload_skill_folder

    db = SessionLocal()
    try:
        user = _admin_user(db)
        upload_skill_folder(
            db,
            user,
            [
                (
                    "SKILL.md",
                    b"---\nname: carbon-market-demo\ndescription: fetch carbon price\n---\n",
                ),
                ("main.py", b"import skill_runtime\nskill_runtime.finish('ok')\n"),
            ],
            replace_existing=True,
        )
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="list_agent_skills",
                arguments={"query": "carbon", "limit": 10},
            )
        )
        payload = json.loads(raw)
        assert payload["ok"] is True
        names = [item["name"] for item in payload["data"]["items"]]
        assert "carbon-market-demo" in names
    finally:
        db.close()


def test_skill_dev_catalog_lists_uploaded_skills():
    ensure_agent_profile_schema(engine)
    from app.services.agent_skill_service import upload_skill_folder
    from app.services.agent_specialist_context import build_specialist_chat_messages

    db = SessionLocal()
    try:
        user = _admin_user(db)
        upload_skill_folder(
            db,
            user,
            [
                (
                    "SKILL.md",
                    b"---\nname: carbon-market-price\ndescription: carbon market\n---\n",
                ),
                ("main.py", b"import skill_runtime\nskill_runtime.finish('1')\n"),
            ],
            replace_existing=True,
        )
        messages = build_specialist_chat_messages(
            db,
            user,
            agent_id="skill-dev",
            message="生成 skill 爬碳价",
            history=None,
        )
        system = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        assert "carbon-market-price" in system
    finally:
        db.close()
