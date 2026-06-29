"""Agent 用户/部门列表确定性回复。"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.database import SessionLocal
from app.models.org import User
from app.services.agent_admin_reply import (
    capture_admin_list_deterministic_reply,
    format_user_list_markdown,
)
from app.services.agent_admin_service import list_users_for_agent
from app.services.agent_reply_synth import synthesize_tool_loop_user_reply


def test_format_user_list_markdown_uses_real_db_fields():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        data = list_users_for_agent(db, admin, page=1, page_size=100)
        md = format_user_list_markdown(db, data)
        assert "zhangsan" not in md.casefold()
        assert "benxi.com" not in md.casefold()
        assert "admin" in md
        assert str(data["total"]) in md
        assert "系统管理员" in md or "admin" in md
    finally:
        db.close()


def test_capture_list_users_sets_deterministic_reply():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        data = list_users_for_agent(db, admin, page=1, page_size=100)
        raw = json.dumps(
            {"ok": True, "summary": "共 12 个用户", "data": data},
            ensure_ascii=False,
        )
        loop_state: dict = {}
        capture_admin_list_deterministic_reply(
            db,
            tool_name="list_users",
            result_text=raw,
            loop_state=loop_state,
        )
        reply = loop_state.get("deterministic_reply") or ""
        assert "zhangsan" not in reply.casefold()
        assert "admin" in reply
    finally:
        db.close()


def test_synthesize_returns_deterministic_reply_without_llm():
    md = "系统中共有 **12** 个用户。\n\n| 用户名 | 显示名 |"
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message="系统中有哪些用户",
            loop_state={"deterministic_reply": md},
        )
    )
    assert reply == md
