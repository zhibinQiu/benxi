"""Tool vs Skill 边界定义 — 全局原子 Tool 池与 Skill 运行时层。

Tool（工具）：最小原子执行单元，无业务语义，不暴露给 LLM。
Skill（技能）：面向业务的封装，可调用 1~N 个 Tool，是子 Agent 对外能力接口。
调度 Agent 仅读取 Skill 元数据；专精 Agent 通过 Skill 运行时层（invoke_skill 等）执行。
"""

from __future__ import annotations

from enum import StrEnum

from app.core.agent_tool_args import (
    ADMIN_DEPT_TOOL_NAMES,
    ADMIN_USER_TOOL_NAMES,
    BROWSER_TOOL_NAMES,
    DOCUMENT_TOOL_NAMES,
    ORCHESTRATION_TOOL_NAMES,
    PLATFORM_TOOL_NAMES,
    RETRIEVAL_TOOL_NAMES,
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
    ORCHESTRATION = "orchestration"


_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    ATOMIC_TOOL_WEB_SEARCH: ToolCategory.WEB,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: ToolCategory.KNOWLEDGE,
    ATOMIC_TOOL_KG_QUERY: ToolCategory.GRAPH,
    "read_agent_memory": ToolCategory.MEMORY,
    "append_agent_memory": ToolCategory.MEMORY,
    "search_documents_by_name": ToolCategory.DOCUMENT,
    "read_document_content": ToolCategory.DOCUMENT,
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


class Layer(StrEnum):
    """能力分层。"""

    GLOBAL_ATOMIC = "global_atomic"  # 内部 Tool 池，Skill handler 调用
    SKILL_RUNTIME = "skill_runtime"  # LLM 可见的 Skill 调度原语
    SKILL = "skill"  # 业务 Skill（经 invoke_skill 或目录 playbook 激活）


# --- 全局原子 Tool（不暴露给 LLM）---

GLOBAL_ATOMIC_TOOL_NAMES: frozenset[str] = frozenset(
    {
        *RETRIEVAL_TOOL_NAMES,
        *DOCUMENT_TOOL_NAMES,
        *PLATFORM_TOOL_NAMES,
        *BROWSER_TOOL_NAMES,
        *ADMIN_USER_TOOL_NAMES,
        *ADMIN_DEPT_TOOL_NAMES,
    }
)

# 记忆读写走文件 I/O，归为原子 Tool
GLOBAL_ATOMIC_TOOL_NAMES = GLOBAL_ATOMIC_TOOL_NAMES | frozenset(
    {"read_agent_memory", "append_agent_memory"}
)

# --- Skill 运行时层（LLM 可见，非业务 Skill 本体）---

SKILL_RUNTIME_TOOL_NAMES: tuple[str, ...] = (
    "invoke_skill",
    "load_uploaded_skill",
    "run_skill_script",
    "create_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
    "list_agent_skills",
    "search_skills",
    "request_orchestrator_assist",
)

# 技能管理 operation（经 invoke_skill(skill-development, call, {operation, params})）
SKILL_MGMT_TOOL_NAMES: tuple[str, ...] = (
    "list_agent_skills",
    "load_uploaded_skill",
    "run_skill_script",
    "create_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
)

# LLM 常见误用名 → 平台 operation
SKILL_MGMT_OPERATION_ALIASES: dict[str, str] = {
    "list_uploaded_skills": "list_agent_skills",
    "list_skills": "list_agent_skills",
}


def normalize_skill_mgmt_operation(operation: str) -> str:
    op = (operation or "").strip()
    return SKILL_MGMT_OPERATION_ALIASES.get(op, op)


def skill_mgmt_operations_hint() -> str:
    return "、".join(SKILL_MGMT_TOOL_NAMES)

NOTIFICATION_TOOL_NAMES: tuple[str, ...] = (
    "send_notification",
    "schedule_notification",
    "list_scheduled_notifications",
    "cancel_scheduled_notification",
)
SKILL_NOTIFICATION = "notification"

# scheduler 专精直接暴露的全局原子 Tool（绕过 invoke_skill 间接调用，避免嵌套参数错误）
_SCHEDULER_ATOMIC_TOOLS: tuple[str, ...] = NOTIFICATION_TOOL_NAMES

# 按专精 id 额外挂载的运行时 Tool
_SKILL_RUNTIME_BY_AGENT: dict[str, frozenset[str]] = {
    "skill-dev": frozenset(
        {
            "invoke_skill",
            "search_skills",
            "invoke_context_subagent",
            "request_orchestrator_assist",
        }
    ),
    "platform": frozenset({"invoke_skill", "search_skills", "request_orchestrator_assist"}),
    "rpa": frozenset(
        {
            "invoke_skill",
            "load_uploaded_skill",
            "run_skill_script",
            "search_skills",
            "invoke_context_subagent",
            "request_orchestrator_assist",
        }
    ),
    "scheduler": frozenset({"invoke_skill", "search_skills", "request_orchestrator_assist"}),
    "orchestrator": frozenset({"invoke_skill", "search_skills", "request_orchestrator_assist"}),
}

# 专精 Agent → 可直接调用的全局原子 Tool 名（绕过 invoke_skill 间接层）
_AGENT_ATOMIC_TOOLS: dict[str, tuple[str, ...]] = {
    "scheduler": _SCHEDULER_ATOMIC_TOOLS,
}

# --- 内置领域 Skill（挂载专精 Agent，catalog 可见性各异）---

SKILL_DOCUMENT_LIBRARY = "document-library"
SKILL_PLATFORM_OPS = "platform-ops"
SKILL_BROWSER_AUTOMATION = "browser-automation"
SKILL_USER_ADMIN = "user-administration"
SKILL_DEPT_ADMIN = "dept-administration"
SKILL_SKILL_DEV = "skill-development"

SKILL_WEB_SEARCH = "web-search"
SKILL_KNOWLEDGE_SEARCH = "knowledge-search"
SKILL_KG_PALANTIR = "kg-palantir"
SKILL_KNOWLEDGE_RESEARCH = "knowledge-research"

SKILL_FREE_WEB_AI_CHAT = "free-web-ai-chat"
SKILL_FREE_WEB_AI_IMAGE = "free-web-ai-image"
SKILL_FREE_WEB_AI_ASK = "free-web-ai-ask-image"

# skill-dev 经 invoke_context_subagent 委托调用的系统 Skill（子 Agent 内 invoke_skill）
SKILL_DEV_AUXILIARY_SKILLS: tuple[str, ...] = (
    SKILL_BROWSER_AUTOMATION,
    SKILL_WEB_SEARCH,
    SKILL_KNOWLEDGE_SEARCH,
    SKILL_KG_PALANTIR,
)


def build_skill_dev_system_access_hint() -> str:
    """skill-dev 系统能力路径提示（注入 prompt）。"""
    return (
        "【skill-dev · 系统能力路径】\n"
        "本专精绑定 skill-development（包 CRUD）；同时前端已挂载 browser-automation，\n"
        "创建抓取类 Skill 时可直接 invoke_skill(browser-automation, call, "
        "{operation: browser_navigate|browser_snapshot|..., params}) 调研页面结构，\n"
        "调研完立即回到技能创建主流程。\n"
        "纯主题检索调研（非浏览器操作）：invoke_context_subagent(kind=explore, queries=[...]) "
        "委托子 Agent 并行 web-search / knowledge-search / kg-palantir。\n"
        "浏览器未开启时 browser-automation 相关调用不可用，须用 explore 替代。\n"
        "技能包操作统一：invoke_skill(skill-development, call, {operation, params})，"
        "operation 含 list_agent_skills、create_skill、run_skill_script 等。"
    )


# 专精 Agent 默认 Skill 绑定
# orchestrator（通用智能体）挂载所有常用/通用 Skill，可直接处理大多数任务。
# 专精 Agent 只挂载领域专属操作 Skill，仅当用户要做专精操作时才需要路由。
AGENT_DEFAULT_SKILLS: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        # 通用检索与AI能力（orchestrator 可直接处理）
        SKILL_WEB_SEARCH,
        SKILL_KNOWLEDGE_SEARCH,
        SKILL_KNOWLEDGE_RESEARCH,
        SKILL_KG_PALANTIR,
        SKILL_FREE_WEB_AI_CHAT,
        SKILL_FREE_WEB_AI_IMAGE,
        SKILL_FREE_WEB_AI_ASK,
        "mermaid-diagram",
    ),
    "platform": (
        # 平台数据操作（文档库/待办/用户部门管理）
        SKILL_DOCUMENT_LIBRARY,
        SKILL_PLATFORM_OPS,
        SKILL_USER_ADMIN,
        SKILL_DEPT_ADMIN,
    ),
    "rpa": (SKILL_BROWSER_AUTOMATION,),
    "scheduler": (SKILL_NOTIFICATION, SKILL_BROWSER_AUTOMATION),
    "skill-dev": (SKILL_SKILL_DEV,),
}

# 内置系统 Skill 名称集合（与 AGENT_DEFAULT_SKILLS 同步，用于路由区分）
BUILTIN_SKILL_NAMES: frozenset[str] = frozenset(
    name for names in AGENT_DEFAULT_SKILLS.values() for name in names
)

# ToolCategory → 领域 Skill（兼容旧 tool_categories 配置的内部解析）
_CATEGORY_TO_DOMAIN_SKILL: dict[ToolCategory, str] = {
    ToolCategory.DOCUMENT: SKILL_DOCUMENT_LIBRARY,
    ToolCategory.PLATFORM: SKILL_PLATFORM_OPS,
    ToolCategory.BROWSER: SKILL_BROWSER_AUTOMATION,
    ToolCategory.ADMIN: SKILL_USER_ADMIN,  # dept 由 user-admin + dept-admin 共同覆盖
    ToolCategory.WEB: SKILL_WEB_SEARCH,
    ToolCategory.KNOWLEDGE: SKILL_KNOWLEDGE_SEARCH,
    ToolCategory.GRAPH: SKILL_KG_PALANTIR,
    ToolCategory.SKILL_MGMT: SKILL_SKILL_DEV,
}

# 检索类 Skill → 内部原子 Tool（Skill handler 调用）
RETRIEVAL_SKILL_ATOMIC_MAP: dict[str, tuple[str, str]] = {
    SKILL_WEB_SEARCH: ("web_search", "search"),
    SKILL_KNOWLEDGE_SEARCH: ("knowledge_retrieve", "retrieve"),
    SKILL_KG_PALANTIR: ("kg_query", "query_entities"),
}

# 全局原子 Tool → 默认归属 Skill（legacy 路由）
TOOL_TO_SKILL_ID: dict[str, str] = {
    atomic: skill
    for skill, (atomic, _) in RETRIEVAL_SKILL_ATOMIC_MAP.items()
}
for _tool in DOCUMENT_TOOL_NAMES:
    TOOL_TO_SKILL_ID[_tool] = SKILL_DOCUMENT_LIBRARY
for _tool in PLATFORM_TOOL_NAMES:
    if _tool not in NOTIFICATION_TOOL_NAMES:
        TOOL_TO_SKILL_ID[_tool] = SKILL_PLATFORM_OPS
for _tool in NOTIFICATION_TOOL_NAMES:
    TOOL_TO_SKILL_ID[_tool] = SKILL_NOTIFICATION
for _tool in BROWSER_TOOL_NAMES:
    TOOL_TO_SKILL_ID[_tool] = SKILL_BROWSER_AUTOMATION
for _tool in ADMIN_USER_TOOL_NAMES:
    TOOL_TO_SKILL_ID[_tool] = SKILL_USER_ADMIN
for _tool in ADMIN_DEPT_TOOL_NAMES:
    TOOL_TO_SKILL_ID[_tool] = SKILL_DEPT_ADMIN
TOOL_TO_SKILL_ID["read_agent_memory"] = SKILL_PLATFORM_OPS
TOOL_TO_SKILL_ID["append_agent_memory"] = SKILL_PLATFORM_OPS


def skill_id_for_tool(tool_id: str) -> str:
    return TOOL_TO_SKILL_ID.get((tool_id or "").strip(), SKILL_PLATFORM_OPS)


def is_global_atomic_tool(name: str) -> bool:
    return (name or "").strip() in GLOBAL_ATOMIC_TOOL_NAMES


def is_skill_runtime_tool(name: str) -> bool:
    return (name or "").strip() in SKILL_RUNTIME_TOOL_NAMES


def skill_runtime_tools_for_agent(agent_id: str) -> frozenset[str]:
    aid = (agent_id or "").strip()
    return _SKILL_RUNTIME_BY_AGENT.get(aid, frozenset({"invoke_skill", "request_orchestrator_assist"}))


def agent_atomic_tool_names(agent_id: str) -> tuple[str, ...]:
    """返回专精 Agent 可直接调用的全局原子 Tool 名。"""
    aid = (agent_id or "").strip()
    return _AGENT_ATOMIC_TOOLS.get(aid, ())


def domain_skills_from_tool_categories(
    categories: tuple[ToolCategory, ...],
) -> set[str]:
    """从旧 tool_categories 推导领域 Skill 集合（迁移兼容）。"""
    names: set[str] = set()
    for cat in categories:
        mapped = _CATEGORY_TO_DOMAIN_SKILL.get(cat)
        if mapped:
            names.add(mapped)
        if cat == ToolCategory.ADMIN:
            names.add(SKILL_DEPT_ADMIN)
    return names
