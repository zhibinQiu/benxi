"""平台 Agent 原子工具目录 — 与 Skill 分离，仅供管理与运行时 tool spec 对齐。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.permissions import user_has_permission
from app.models.org import User
from app.schemas.agent_skill import AgentToolCategoryOut, AgentToolOut
from app.services.agent_tools import (
    AGENT_TOOL_SPECS,
    _ADMIN_DEPT_TOOL_SPECS,
    _ADMIN_USER_TOOL_SPECS,
    _ATOMIC_RETRIEVAL_TOOL_SPECS,
    _BROWSER_TOOL_SPECS,
    _DOCUMENT_TOOL_SPECS,
    _PLATFORM_TOOL_SPECS,
    _RUN_SKILL_SCRIPT_SPEC,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)


class ToolCategory(StrEnum):
    WEB = "web"
    KNOWLEDGE = "knowledge"
    GRAPH = "graph"
    SKILL_MGMT = "skill_mgmt"
    MEMORY = "memory"
    DOCUMENT = "document"
    PLATFORM = "platform"
    ADMIN = "admin"
    BROWSER = "browser"


_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    ATOMIC_TOOL_WEB_SEARCH: ToolCategory.WEB,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: ToolCategory.KNOWLEDGE,
    ATOMIC_TOOL_KG_QUERY: ToolCategory.GRAPH,
    "load_uploaded_skill": ToolCategory.SKILL_MGMT,
    "create_uploaded_skill": ToolCategory.SKILL_MGMT,
    "update_uploaded_skill_file": ToolCategory.SKILL_MGMT,
    "delete_uploaded_skill": ToolCategory.SKILL_MGMT,
    "run_skill_script": ToolCategory.SKILL_MGMT,
    "read_agent_memory": ToolCategory.MEMORY,
    "append_agent_memory": ToolCategory.MEMORY,
    "list_library_documents": ToolCategory.DOCUMENT,
    "list_manageable_documents": ToolCategory.DOCUMENT,
    "list_document_folders": ToolCategory.DOCUMENT,
    "create_kb_folder": ToolCategory.DOCUMENT,
    "create_library_document": ToolCategory.DOCUMENT,
    "update_kb_folder": ToolCategory.DOCUMENT,
    "delete_kb_folder": ToolCategory.DOCUMENT,
    "sync_document_knowledge": ToolCategory.DOCUMENT,
    "reindex_document": ToolCategory.DOCUMENT,
    "rename_document": ToolCategory.DOCUMENT,
    "move_document": ToolCategory.DOCUMENT,
    "share_document": ToolCategory.DOCUMENT,
    "delete_document": ToolCategory.DOCUMENT,
    "list_todos": ToolCategory.PLATFORM,
    "create_todo": ToolCategory.PLATFORM,
    "update_todo": ToolCategory.PLATFORM,
    "delete_todo": ToolCategory.PLATFORM,
    "send_notification": ToolCategory.PLATFORM,
    "schedule_notification": ToolCategory.PLATFORM,
    "list_scheduled_notifications": ToolCategory.PLATFORM,
    "cancel_scheduled_notification": ToolCategory.PLATFORM,
    "list_users": ToolCategory.ADMIN,
    "create_user": ToolCategory.ADMIN,
    "update_user": ToolCategory.ADMIN,
    "delete_user": ToolCategory.ADMIN,
    "list_departments": ToolCategory.ADMIN,
    "create_department": ToolCategory.ADMIN,
    "update_department": ToolCategory.ADMIN,
    "delete_department": ToolCategory.ADMIN,
    "browser_navigate": ToolCategory.BROWSER,
    "browser_snapshot": ToolCategory.BROWSER,
    "browser_click": ToolCategory.BROWSER,
    "browser_type": ToolCategory.BROWSER,
    "browser_fill": ToolCategory.BROWSER,
    "browser_screenshot": ToolCategory.BROWSER,
    "browser_save_workflow": ToolCategory.BROWSER,
    "browser_close_session": ToolCategory.BROWSER,
    "browser_replay_workflow": ToolCategory.BROWSER,
    "browser_run_task": ToolCategory.BROWSER,
    "schedule_browser_workflow": ToolCategory.BROWSER,
}


def _all_tool_specs() -> list[dict[str, Any]]:
    """管理页展示完整原子工具清单（含运行时按开关隐藏的项）。"""
    return [
        *_ATOMIC_RETRIEVAL_TOOL_SPECS,
        *AGENT_TOOL_SPECS,
        _RUN_SKILL_SCRIPT_SPEC,
        *_DOCUMENT_TOOL_SPECS,
        *_PLATFORM_TOOL_SPECS,
        *_ADMIN_USER_TOOL_SPECS,
        *_ADMIN_DEPT_TOOL_SPECS,
        *_BROWSER_TOOL_SPECS,
    ]


def _availability(
    db: Session, name: str, *, user: User | None
) -> tuple[bool, str]:
    from app.config import get_settings
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config
    from app.services.searxng_service import is_enabled as web_search_enabled

    if name == ATOMIC_TOOL_WEB_SEARCH:
        if web_search_enabled(db):
            return True, ""
        return False, "联网搜索（SearXNG）未启用"
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        if user is None or user_has_permission(db, user, "feature.knowledge_search"):
            return True, ""
        return False, "当前用户无知识库检索权限"
    if name == ATOMIC_TOOL_KG_QUERY:
        if user is None or user_has_permission(db, user, "feature.kg_palantir"):
            return True, ""
        return False, "当前用户无本体图谱权限"
    if name == "run_skill_script":
        if get_settings().agent_skill_script_enabled:
            return True, ""
        return False, "平台未开启 agent_skill_script_enabled"
    if name.startswith("browser_") or name == "schedule_browser_workflow":
        if get_browser_rpa_config(db).enabled:
            return True, ""
        return False, "浏览器 RPA 未在系统设置中启用"
    return True, ""


def list_agent_tools(
    db: Session,
    *,
    user: User | None = None,
) -> list[AgentToolOut]:
    """返回平台全部原子 Agent 工具（含当前不可用项及原因）。"""
    items: list[AgentToolOut] = []
    for spec in _all_tool_specs():
        fn = spec.get("function") or {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        category = _TOOL_CATEGORIES.get(name, ToolCategory.PLATFORM)
        available, note = _availability(db, name, user=user)
        items.append(
            AgentToolOut(
                name=name,
                description=str(fn.get("description") or ""),
                category=AgentToolCategoryOut(category.value),
                available=available,
                availability_note=note,
            )
        )
    return items
