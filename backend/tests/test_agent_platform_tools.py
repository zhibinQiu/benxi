"""智能体平台管理工具。"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.agent_tools import agent_tool_names, build_agent_tool_specs


def test_platform_tools_registered_without_user_dept_sql():
    names = agent_tool_names()
    for tool in (
        "sync_document_knowledge",
        "reindex_document",
        "update_kb_folder",
        "list_todos",
    ):
        assert tool in names
    for tool in (
        "list_users",
        "create_user",
        "update_user",
        "delete_user",
        "list_departments",
        "create_department",
        "update_department",
        "delete_department",
    ):
        assert tool not in names


def test_build_agent_tool_specs_excludes_user_dept_sql():
    db = MagicMock()
    user = MagicMock()
    specs = {s["function"]["name"] for s in build_agent_tool_specs(db, user)}
    assert "create_user" not in specs
    assert "create_department" not in specs
    assert "list_users" not in specs
