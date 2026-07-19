"""Agent 工具动态发现。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.tool_skill_taxonomy import (
    PARENT_HIDDEN_EXECUTION_ENTRYPOINTS,
    mounted_tool_names_for_agent,
)
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


def test_select_visible_exposes_mounted_specs_only():
    specs = [
        {"type": "function", "function": {"name": "web_search", "description": "y"}},
        {"type": "function", "function": {"name": "browser_navigate", "description": "z"}},
    ]
    visible = select_visible_tool_specs(specs, agent_id="orchestrator")
    names = {tool_spec_name(s) for s in visible}
    assert "web_search" in names
    assert "browser_navigate" in names
    # 未传入 specs 的工具不可见（可见集=已挂载 specs）
    assert "create_kb_folder" not in names
    assert "find_skills" not in names


def test_skill_dev_does_not_expose_run_tool_batch():
    specs = [
        {"type": "function", "function": {"name": "run_skill_script", "description": "x"}},
        {"type": "function", "function": {"name": "list_agent_skills", "description": "y"}},
    ]
    visible = select_visible_tool_specs(specs, agent_id="skill-dev")
    names = {tool_spec_name(s) for s in visible}
    assert "run_skill_script" in names
    assert "run_tool_batch" not in names


def test_core_tool_names_include_orchestration_primitives():
    assert "find_skills" in CORE_TOOL_NAMES
    assert "invoke_context_subagent" in CORE_TOOL_NAMES
    assert "run_skill_script" not in CORE_TOOL_NAMES


def test_parent_orchestrator_specs_are_mounted_not_platform_wide():
    db = MagicMock()
    user = MagicMock()
    mounted_default = mounted_tool_names_for_agent("orchestrator")
    with (
        patch(
            "app.services.agent_profile_service.resolve_effective_runtime_tool_names",
            return_value=list(mounted_default),
        ),
        patch("app.services.agent_tools.user_has_permission", return_value=False),
        patch("app.domains.knowledge.knowledge.enabled", return_value=True),
        patch(
            "app.integrations.browser_automation.browser_config.get_browser_rpa_config",
        ) as browser_cfg,
    ):
        browser_cfg.return_value.enabled = True
        specs = build_agent_tool_specs(db, user, agent_id="orchestrator")
    names = {tool_spec_name(s) for s in specs}
    assert "find_skills" in names
    assert "web_search" in names
    assert "browser_navigate" in names
    # 未挂载到 orchestrator 的平台工具不应出现
    assert "create_user" not in names
    assert "create_skill" not in names
    for hidden in PARENT_HIDDEN_EXECUTION_ENTRYPOINTS:
        assert hidden not in names, hidden
    # 可见集 ⊆ 默认挂载集（再减去隐藏入口）
    assert names <= (mounted_default - PARENT_HIDDEN_EXECUTION_ENTRYPOINTS)
