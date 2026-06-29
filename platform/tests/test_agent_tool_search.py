"""Agent 工具动态发现。"""

from __future__ import annotations

from app.services.agent_tool_search import (
    CORE_TOOL_NAMES,
    search_tool_definitions,
    select_visible_tool_specs,
    tool_spec_name,
)
from app.services.agent_tools import build_agent_tool_specs


def test_search_tools_finds_document_tools():
    specs = [
        {
            "type": "function",
            "function": {
                "name": "create_kb_folder",
                "description": "在文档库创建文件夹",
            },
        },
        {
            "type": "function",
            "function": {"name": "list_todos", "description": "列出待办"},
        },
    ]
    hits = search_tool_definitions(specs, "文档 文件夹")
    names = {tool_spec_name(s) for s in hits}
    assert "create_kb_folder" in names


def test_select_visible_includes_core_and_unlocked():
    specs = [
        {"type": "function", "function": {"name": "create_kb_folder", "description": "x"}},
        {"type": "function", "function": {"name": "web_search", "description": "y"}},
    ]
    visible = select_visible_tool_specs(specs, {"create_kb_folder"})
    names = {tool_spec_name(s) for s in visible}
    assert "search_tools" in names
    assert "web_search" in names
    assert "create_kb_folder" in names
    assert "list_todos" not in names


def test_core_tool_names_subset_of_full_catalog():
    assert "search_tools" in CORE_TOOL_NAMES
    assert "knowledge_retrieve" in CORE_TOOL_NAMES
    assert "search_documents_by_name" in CORE_TOOL_NAMES
    assert "run_skill_script" not in CORE_TOOL_NAMES
