"""调度层协助与续办（星型编排）。"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.aip.handoff import (
    build_specialist_assist_handoff,
    orchestrator_assist_from_complete,
)
from app.core.aip.messaging import attach_handoff_to_complete
from app.core.phone import bootstrap_login_id
from app.database import SessionLocal, engine
from app.models.org import User
from app.schema_migrate import ensure_agent_profile_schema
from app.services.agent_orchestrator import (
    OrchestratorTask,
    build_assist_resume_message,
    build_helper_assist_message,
    resolve_assist_agent_id,
)
from app.services.agent_profile_service import resolve_agent_tool_names
from app.services.agent_tools import execute_agent_tool


def test_request_orchestrator_assist_direct_call():
    """platform 专精直接暴露 request_orchestrator_assist。"""
    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        loop_state = {
            "agent_id": "platform",
            "allowed_skill_names": {"document-library", "platform-ops"},
            "tool_outcome_lines": ["列出文档失败"],
        }
        raw = asyncio.run(
            execute_agent_tool(
                db,
                user,
                tool_name="request_orchestrator_assist",
                arguments={
                    "reason": "需要读取文档库正文",
                    "needed_from": "知识库检索",
                    "suggested_agent_id": "platform",
                },
                loop_state=loop_state,
            )
        )
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert loop_state.get("orchestrator_assist_request") is not None
        assert loop_state["orchestrator_assist_request"]["suggested_agent_id"] == "platform"
    finally:
        db.close()


def test_platform_profile_has_orchestrator_assist_tool():
    db = SessionLocal()
    try:
        names = resolve_agent_tool_names(db, "platform")
        assert "request_orchestrator_assist" in names
        assert "consult_specialist" not in names
    finally:
        db.close()


def test_orchestrator_assist_handoff_roundtrip():
    assist = {
        "reason": "需要读取文档库正文",
        "needed_from": "知识库检索",
        "suggested_agent_id": "platform",
    }
    handoff = build_specialist_assist_handoff(
        {"tool_outcome_lines": ["列出文档：失败"]},
        agent_id="platform",
        session_id="sess-1",
        task_id="t1",
        assist=assist,
    )
    assert handoff.ok
    complete = attach_handoff_to_complete({"type": "complete"}, handoff.message)
    parsed = orchestrator_assist_from_complete(complete)
    assert parsed is not None
    assert parsed.get("suggested_agent_id") == "platform"


def test_resolve_assist_agent_from_suggestion():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="test"
    )
    assist = {
        "reason": "缺检索",
        "needed_from": "政策调研",
        "suggested_agent_id": "platform",
    }
    assert resolve_assist_agent_id(assist, task, "用户问题") == "platform"


def test_resolve_assist_skips_same_agent():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="test"
    )
    assist = {
        "reason": "还要操作",
        "needed_from": "平台",
        "suggested_agent_id": "platform",
    }
    assert resolve_assist_agent_id(assist, task, "用户问题") is None


def test_build_helper_and_resume_messages():
    task = OrchestratorTask(
        id="t1", title="报告撰写", agent_id="report", reason="test"
    )
    assist = {"reason": "缺材料", "needed_from": "知识库检索"}
    helper = build_helper_assist_message("写碳市场报告", task, assist)
    assert "调度协调" in helper
    assert "知识库检索" in helper

    resume = build_assist_resume_message(
        session_id="sess-x",
        task_id="t1",
        target_agent_id="report",
        user_message="写碳市场报告",
        helper_title="检索研究",
        helper_summary="找到 3 份政策文件",
    )
    assert "续办" in resume
    assert "检索研究" in resume
