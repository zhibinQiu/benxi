"""智能体平台管理工具。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.agent_tools import agent_tool_names, build_agent_tool_specs


def test_admin_tools_registered():
    names = agent_tool_names()
    for tool in (
        "sync_document_knowledge",
        "reindex_document",
        "update_kb_folder",
        "list_users",
        "create_department",
    ):
        assert tool in names


def test_build_agent_tool_specs_gates_admin_by_permission():
    db = MagicMock()
    admin = MagicMock()
    member = MagicMock()

    with patch(
        "app.services.agent_tools.user_has_permission",
        side_effect=lambda _db, user, code: user is admin
        and code in ("admin.user", "admin.dept"),
    ):
        admin_specs = {
            s["function"]["name"] for s in build_agent_tool_specs(db, admin)
        }
        member_specs = {
            s["function"]["name"] for s in build_agent_tool_specs(db, member)
        }

    assert "create_user" in admin_specs
    assert "create_department" in admin_specs
    assert "create_user" not in member_specs
