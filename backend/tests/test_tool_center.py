"""ToolCenter 标准规约测试。"""

from __future__ import annotations

import asyncio

from app.core.tool_skill_taxonomy import GLOBAL_ATOMIC_TOOL_NAMES
from app.tool_center.errors import ToolErrorCode, business_message, is_retryable
from app.tool_center.registry import get_tool_center
from app.tool_center.schemas import SkillMeta, ToolCallRequest, ToolDescriptor, ToolResponse
from app.tool_center.context import ToolRuntimeContext
from app.tool_center.executor import execute_tool_call, new_call_id


def test_tool_descriptor_schema():
    desc = ToolDescriptor(
        tool_id="db_mysql_query",
        tool_type="io_database",
        description="执行MySQL只读查询，仅支持SELECT语句",
        input_schema={
            "type": "object",
            "required": ["sql"],
            "properties": {
                "sql": {"type": "string", "desc": "查询SQL，禁止DELETE/DROP/ALTER"},
                "timeout": {"type": "integer", "default": 10},
            },
        },
        output_schema={
            "rows": "list[dict]",
            "column_names": "list[str]",
            "total": "int",
        },
        rate_limit={"qps": 20},
    )
    assert desc.tool_id == "db_mysql_query"
    assert desc.rate_limit.qps == 20


def test_tool_call_request_structure():
    req = ToolCallRequest(
        call_id="skill_subtask_xxxx",
        tool_id="web_search",
        params={"query": "test", "max_items": 8},
        trace_id="global_task_001",
        skill_meta=SkillMeta(skill_id="web_search", belong_agent="research"),
    )
    assert req.skill_meta.skill_id == "web_search"


def test_tool_response_success_and_failure():
    ok = ToolResponse(
        success=True,
        code=0,
        msg="execute success",
        data={"rows": [{"amount": 12000}]},
        meta={"cost_ms": 120, "tool_version": "v1.2"},
    )
    assert ok.retryable is False

    fail = ToolResponse(
        success=False,
        code=10005,
        msg="SQL包含禁止操作DROP",
        detail="DELETE/DROP/ALTER 语句不允许执行",
        meta={"cost_ms": 5, "retryable": False},
    )
    assert fail.retryable is False


def test_error_code_retryable():
    assert is_retryable(ToolErrorCode.RATE_LIMITED)
    assert is_retryable(ToolErrorCode.TIMEOUT)
    assert not is_retryable(ToolErrorCode.PARAM_INVALID)
    assert "参数" in business_message(ToolErrorCode.PARAM_INVALID)


def test_registry_bootstraps_global_atomic_tools():
    center = get_tool_center()
    center.bootstrap()
    ids = {d.tool_id for d in center.list_descriptors()}
    assert "web_search" in ids
    assert "list_todos" in ids
    # 现在注册所有 TOOL_DEFINITIONS 工具，包含 scope 工具名
    assert GLOBAL_ATOMIC_TOOL_NAMES <= ids
    assert "invoke_skill" in ids
    assert "search_skills" in ids

    web = center.get("web_search")
    assert web is not None
    assert web.tool_type == "io_http"
    assert "query" in (web.input_schema.get("properties") or {})


def test_param_validation_returns_1xxx():
    from sqlalchemy import select

    from app.core.phone import bootstrap_login_id
    from app.database import SessionLocal, engine
    from app.models.org import User
    from app.schema_migrate import ensure_agent_profile_schema

    ensure_agent_profile_schema(engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        req = ToolCallRequest(
            call_id=new_call_id(),
            tool_id="web_search",
            params={},
            trace_id="t2",
            skill_meta=SkillMeta(skill_id="web-search", belong_agent="research"),
        )
        resp = asyncio.run(
            execute_tool_call(req, ToolRuntimeContext(db=db, user=user))
        )
        assert resp.success is False
        assert 1000 <= resp.code < 2000
    finally:
        db.close()


def test_skill_bridge_retries_retryable_errors(monkeypatch):
    """Skill 层对可重试 Tool 错误自动退避重试。"""
    from app.skills.types import SkillInvocationContext
    from app.tool_center import skill_bridge

    calls: list[int] = []

    async def _fake_execute(_req, _ctx):
        calls.append(1)
        if len(calls) < 3:
            return ToolResponse(
                success=False,
                code=int(ToolErrorCode.RATE_LIMITED),
                msg="rate limited",
                meta={"retryable": True},
            )
        return ToolResponse(success=True, code=0, msg="ok", data={"hits": 1})

    async def _noop_sleep(_s):
        return None

    monkeypatch.setattr(skill_bridge, "execute_tool_call", _fake_execute)
    monkeypatch.setattr(skill_bridge.asyncio, "sleep", _noop_sleep)

    ctx = SkillInvocationContext(db=None, user=None)  # type: ignore[arg-type]
    result = asyncio.run(
        skill_bridge.invoke_atomic_tool(
            ctx,
            tool_id="web_search",
            params={"query": "test"},
            skill_id="web-search",
        )
    )
    assert result.ok is True
    assert len(calls) == 3
