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
    "fetch_url_content": ToolCategory.WEB,
    "mermaid_diagram": ToolCategory.ORCHESTRATION,
    "carbon_qa_query": ToolCategory.KNOWLEDGE,
}


class Layer(StrEnum):
    """能力分层。"""

    GLOBAL_ATOMIC = "global_atomic"  # 内部 Tool 池，Skill handler 调用
    SKILL_RUNTIME = "skill_runtime"  # LLM 可见的 Skill 调度原语
    SKILL = "skill"  # 业务 Skill（经 invoke_skill 或目录 playbook 激活）


class ToolScope(StrEnum):
    """工具可见性范围。

    - ORCHESTRATOR: 调度智能体可见（describe_tool 可发现）
    - SPECIALIST: 仅专精 Agent 可见
    - ADMIN: 仅管理员可用（需权限检查）
    - INTERNAL: 完全隐藏（仅 Skill handler 内部调用）
    """

    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"
    ADMIN = "admin"
    INTERNAL = "internal"


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

# 原工具类技能迁移为原子 Tool
GLOBAL_ATOMIC_TOOL_NAMES = GLOBAL_ATOMIC_TOOL_NAMES | frozenset(
    {"carbon_qa_query", "mermaid_diagram"}
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

# ── 各智能体默认工具列表（首次使用时写入 DB runtime_tool_names，之后可由多智能体界面编辑）───
# 当无 DB binding 时以此生效；绑定中存在 runtime_tool_names 时覆盖该列表。
DEFAULT_AGENT_TOOLS: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        # skill 运行时层
        "invoke_skill",
        "load_uploaded_skill",
        "run_skill_script",
        "create_skill",
        "update_uploaded_skill_file",
        "delete_uploaded_skill",
        "list_agent_skills",
        "search_skills",
        "request_orchestrator_assist",
        # 编排
        "ask_user_choice",
        # 通知
        "send_notification",
        "schedule_notification",
        "list_scheduled_notifications",
        "cancel_scheduled_notification",
        # 原子工具
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "mermaid_diagram",
        "carbon_qa_query",
        "read_agent_memory",
        "append_agent_memory",
        "fetch_url_content",
    ),
    "platform": (
        "invoke_skill",
        "search_skills",
        "request_orchestrator_assist",
        *DOCUMENT_TOOL_NAMES,
        *PLATFORM_TOOL_NAMES,
        *NOTIFICATION_TOOL_NAMES,
        "read_agent_memory",
        "append_agent_memory",
    ),
    "rpa": (
        "invoke_skill",
        "load_uploaded_skill",
        "run_skill_script",
        "search_skills",
        "invoke_context_subagent",
        "request_orchestrator_assist",
        *BROWSER_TOOL_NAMES,
    ),
    "carbon": (
        "invoke_skill",
        "search_skills",
        "invoke_context_subagent",
        "request_orchestrator_assist",
        "carbon_qa_query",
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "read_agent_memory",
        "append_agent_memory",
    ),
    "skill-dev": (
        "invoke_skill",
        "search_skills",
        "invoke_context_subagent",
        "request_orchestrator_assist",
    ),
    "report": (
        "invoke_skill",
        "request_orchestrator_assist",
    ),
    "power-economy": (
        "invoke_skill",
        "search_skills",
        "invoke_context_subagent",
        "request_orchestrator_assist",
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "read_agent_memory",
        "append_agent_memory",
    ),
}

# orchestrator（通用调度智能体）：一步完成的原子工具直接暴露，无需 invoke_skill 间接层
_ORCHESTRATOR_ATOMIC_TOOLS: tuple[str, ...] = (
    "web_search",
    "knowledge_retrieve",
    "kg_query",
    "mermaid_diagram",
    "carbon_qa_query",
    "read_agent_memory",
    "append_agent_memory",
    "ask_user_choice",
    "fetch_url_content",
)

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
    "orchestrator": frozenset({"search_skills", "request_orchestrator_assist"}),  # 路由专精需要
    "carbon": frozenset(
        {
            "invoke_skill",
            "search_skills",
            "invoke_context_subagent",
            "request_orchestrator_assist",
        }
    ),
    "power-economy": frozenset(
        {
            "invoke_skill",
            "search_skills",
            "invoke_context_subagent",
            "request_orchestrator_assist",
        }
    ),
}

# 专精 Agent → 可直接调用的全局原子 Tool 名（绕过 invoke_skill 间接层）
_AGENT_ATOMIC_TOOLS: dict[str, tuple[str, ...]] = {
    "orchestrator": _ORCHESTRATOR_ATOMIC_TOOLS,
    "platform": (
        *DOCUMENT_TOOL_NAMES,
        # todo/通知/记忆工具
        *PLATFORM_TOOL_NAMES,
        *NOTIFICATION_TOOL_NAMES,
        "read_agent_memory",
        "append_agent_memory",
        # 部门/用户管理（ToolScope ADMIN 需解锁）
    ),
    "rpa": BROWSER_TOOL_NAMES,
    "carbon": (
        "carbon_qa_query",
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "read_agent_memory",
        "append_agent_memory",
    ),
    "power-economy": (
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "read_agent_memory",
        "append_agent_memory",
    ),
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

SKILL_CARBON_QA = "carbon-qa"
SKILL_FREE_WEB_AI = "free-web-ai"

# skill-dev 经 invoke_context_subagent 委托调用的系统能力（保留向后兼容）
SKILL_DEV_AUXILIARY_SKILLS: tuple[str, ...] = ()


def build_skill_dev_system_access_hint() -> str:
    """skill-dev 系统能力路径提示（注入 prompt）。"""
    return (
        "【skill-dev · 系统能力路径】\n"
        "本专精绑定 skill-development（包 CRUD）；创建抓取类 Skill 时可直接调用浏览器原子工具"
        "（browser_navigate, browser_snapshot, browser_click 等）调研页面结构，"
        "调研完立即回到技能创建主流程。\n"
        "纯主题检索调研（非浏览器操作）：invoke_context_subagent(kind=explore, queries=[...]) "
        "委托子 Agent 并行 web_search / knowledge_retrieve / kg_query。\n"
        "浏览器未开启时浏览器相关工具不可用，须用 explore 替代。\n"
        "技能包操作统一：invoke_skill(skill-development, call, {operation, params})，"
        "operation 含 list_agent_skills、create_skill、run_skill_script 等。"
    )


# 专精 Agent 默认 Skill 绑定（仅用于倒排索引，非工具白名单）
# 工具类能力已迁移至原子 Tool，通过 _AGENT_ATOMIC_TOOLS 直接分配。
AGENT_DEFAULT_SKILLS: dict[str, tuple[str, ...]] = {
    "skill-dev": (SKILL_SKILL_DEV,),
}

# 内置系统 Skill 名称集合（仅含真实编排/指令型 Skill）
BUILTIN_SKILL_NAMES: frozenset[str] = frozenset({
    SKILL_SKILL_DEV,
})

# ToolCategory → 领域标识（兼容旧 tool_categories 配置的内部解析）
_CATEGORY_TO_DOMAIN_SKILL: dict[ToolCategory, str] = {
    ToolCategory.SKILL_MGMT: SKILL_SKILL_DEV,
}

# 检索类 Skill → 内部原子 Tool（保留仅作向后兼容）
RETRIEVAL_SKILL_ATOMIC_MAP: dict[str, tuple[str, str]] = {}

# 全局原子 Tool → 默认归属（用于 tool → agent 归因）
TOOL_TO_SKILL_ID: dict[str, str] = {}
# 检索工具 → 通用归类
for name in ("web_search", "knowledge_retrieve", "kg_query", "carbon_qa_query", "mermaid_diagram"):
    TOOL_TO_SKILL_ID[name] = SKILL_KNOWLEDGE_RESEARCH

# ── 工具可见性范围（分层控制） ──────────────────────────────────────────────
# 控制 LLM 通过 describe_tool 能否发现该工具。
# 缺失的工具默认视为 ORCHESTRATOR 可见（兼容旧配置）。

_TOOL_SCOPE: dict[str, ToolScope] = {
    # --- 管理员工具栏：仅管理员可用，orchestrator 不可发现 ---
    "list_users": ToolScope.ADMIN,
    "create_user": ToolScope.ADMIN,
    "update_user": ToolScope.ADMIN,
    "delete_user": ToolScope.ADMIN,
    "list_departments": ToolScope.ADMIN,
    "create_department": ToolScope.ADMIN,
    "update_department": ToolScope.ADMIN,
    "delete_department": ToolScope.ADMIN,
    # --- 专精专用工具：仅路由到对应 Agent 后可见 ---
    "schedule_browser_workflow": ToolScope.SPECIALIST,
    "browser_navigate": ToolScope.SPECIALIST,
    "browser_snapshot": ToolScope.SPECIALIST,
    "browser_click": ToolScope.SPECIALIST,
    "browser_type": ToolScope.SPECIALIST,
    "browser_fill": ToolScope.SPECIALIST,
    "browser_screenshot": ToolScope.SPECIALIST,
    "browser_save_workflow": ToolScope.SPECIALIST,
    "browser_close_session": ToolScope.SPECIALIST,
    "browser_replay_workflow": ToolScope.SPECIALIST,
    "browser_run_task": ToolScope.SPECIALIST,
    "create_skill": ToolScope.SPECIALIST,
    "load_uploaded_skill": ToolScope.SPECIALIST,
    "run_skill_script": ToolScope.SPECIALIST,
    "update_uploaded_skill_file": ToolScope.SPECIALIST,
    "delete_uploaded_skill": ToolScope.SPECIALIST,
    # --- 通用工具：默认 orchestrator 可见（省略写法） ---
}


def get_tool_scope(name: str) -> ToolScope:
    """返回工具的可见性范围，未配置时默认 ORCHESTRATOR 可见。"""
    return _TOOL_SCOPE.get((name or "").strip(), ToolScope.ORCHESTRATOR)


def is_tool_visible_to_agent(name: str, agent_id: str | None) -> bool:
    """判断指定工具是否对当前 Agent 可见。

    规则：
    - orchestrator 可见范围：ORCHESTRATOR 范围的工具
    - 专精 Agent 可见范围：ORCHESTRATOR + SPECIALIST
    - ADMIN 范围：需要额外权限检查
    - INTERNAL 范围：任何 LLM 均不可见
    """
    scope = get_tool_scope(name)
    if scope == ToolScope.INTERNAL:
        return False
    aid = (agent_id or "").strip().lower()
    if aid == "orchestrator" or not aid:
        return scope == ToolScope.ORCHESTRATOR
    return scope in (ToolScope.ORCHESTRATOR, ToolScope.SPECIALIST)


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
    """从旧 tool_categories 推导领域标识集合（迁移兼容）。"""
    names: set[str] = set()
    for cat in categories:
        mapped = _CATEGORY_TO_DOMAIN_SKILL.get(cat)
        if mapped:
            names.add(mapped)
        if cat == ToolCategory.ADMIN:
            names.add(SKILL_DEPT_ADMIN)
    return names
