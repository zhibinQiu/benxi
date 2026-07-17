"""独立上下文 Subagent 与按需 Skill 目录。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.agent_tool_args import validate_tool_arguments
from app.core.phone import bootstrap_login_id
from app.core.tool_skill_taxonomy import skill_runtime_tools_for_agent
from app.database import SessionLocal
from app.models.org import User
from app.skills.catalog import build_agent_catalog_prompt
from app.core.agent.routing import is_routing_ambiguous


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_lazy_catalog_omits_full_skill_list():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        text = build_agent_catalog_prompt(db, user=user, lazy=True, query="")
        assert "按需发现" in text
        assert "search_skills" in text
        assert "### 内置" not in text
    finally:
        db.close()


def test_lazy_catalog_includes_query_matches():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        text = build_agent_catalog_prompt(
            db,
            user=user,
            query="文档库 文件夹",
            lazy=True,
            preview_limit=4,
        )
        assert "本轮相关 Skill" in text
    finally:
        db.close()


def test_research_has_context_subagent_tool():
    names = skill_runtime_tools_for_agent("research")
    assert "invoke_context_subagent" in names


def test_invoke_context_subagent_args_validation():
    _, err = validate_tool_arguments(
        "invoke_context_subagent",
        {"kind": "search", "task": "检索双碳政策"},
    )
    assert err is None
    _, bad = validate_tool_arguments(
        "invoke_context_subagent",
        {"kind": "invalid", "task": "x"},
    )
    assert bad is not None


def test_invoke_context_subagent_args_parallel_queries():
    _, err = validate_tool_arguments(
        "invoke_context_subagent",
        {
            "kind": "search",
            "queries": ["双碳政策", "碳市场行情", "RPA 行业"],
        },
    )
    assert err is None
