"""Tool vs Skill 边界定义 — 全局原子 Tool 池与智能体工具配置。

Tool（工具）：最小原子执行单元。
Skill（技能）：面向业务的封装，通过 invoke_skill 调用。
智能体工具：每个智能体可直接调用的原子工具集合。
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
    SKILL_RUNTIME_TOOL_NAMES,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)


class ToolCategory(StrEnum):
    """工具分类标签（用于前端/API 工具目录展示）。

    平台 — 平台运营与编排（记忆、待办、通知、管理员、技能编排/管理、元工具等）。
    数据 — 网站拉取/爬取、外部行情与领域取数、知识库/图谱检索等数据处理。
    模型 — 预留，后续对接算法模型推理。
    浏览器 — 浏览器自动化交互（导航/点击/填表等）。
    文档 — 文档库 CRUD 及全文阅读。
    """
    PLATFORM = "platform"
    DATA = "data"
    MODEL = "model"
    BROWSER = "browser"
    DOCUMENT = "document"


# ── 工具分类（供 tool_center/registry.py 和 agent_tool_registry.py 使用，非唯一源）──
_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    # ── 数据（网站拉取/爬取、外部行情、领域取数、知识检索）──
    ATOMIC_TOOL_WEB_SEARCH: ToolCategory.DATA,
    "fetch_url_content": ToolCategory.DATA,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: ToolCategory.DATA,
    ATOMIC_TOOL_KG_QUERY: ToolCategory.DATA,
    "knowledge_folder_search": ToolCategory.DATA,
    "list_mounted_folders": ToolCategory.DATA,
    "stock_quote": ToolCategory.DATA,
    "stock_kline": ToolCategory.DATA,
    "market_indices": ToolCategory.DATA,
    "finance_search": ToolCategory.DATA,
    "f10_data": ToolCategory.DATA,
    "carbon_price": ToolCategory.DATA,
    "carbon_policy": ToolCategory.DATA,
    "carbon_data": ToolCategory.DATA,
    # ── 平台（记忆、待办、通知、管理、编排、技能、元工具）──
    "read_agent_memory": ToolCategory.PLATFORM,
    "append_agent_memory": ToolCategory.PLATFORM,
    "list_todos": ToolCategory.PLATFORM,
    "create_todo": ToolCategory.PLATFORM,
    "update_todo": ToolCategory.PLATFORM,
    "delete_todo": ToolCategory.PLATFORM,
    "send_notification": ToolCategory.PLATFORM,
    "schedule_notification": ToolCategory.PLATFORM,
    "list_scheduled_notifications": ToolCategory.PLATFORM,
    "cancel_scheduled_notification": ToolCategory.PLATFORM,
    "list_users": ToolCategory.PLATFORM,
    "create_user": ToolCategory.PLATFORM,
    "update_user": ToolCategory.PLATFORM,
    "delete_user": ToolCategory.PLATFORM,
    "list_departments": ToolCategory.PLATFORM,
    "create_department": ToolCategory.PLATFORM,
    "update_department": ToolCategory.PLATFORM,
    "delete_department": ToolCategory.PLATFORM,
    "mermaid_diagram": ToolCategory.PLATFORM,
    "invoke_skill": ToolCategory.PLATFORM,
    "find_skills": ToolCategory.PLATFORM,
    "describe_tool": ToolCategory.PLATFORM,
    "search_tools": ToolCategory.PLATFORM,
    "run_tool_batch": ToolCategory.PLATFORM,
    "invoke_context_subagent": ToolCategory.PLATFORM,
    "ask_user_choice": ToolCategory.PLATFORM,
    "request_orchestrator_assist": ToolCategory.PLATFORM,
    "list_agent_skills": ToolCategory.PLATFORM,
    "load_uploaded_skill": ToolCategory.PLATFORM,
    "run_skill_script": ToolCategory.PLATFORM,
    "create_skill": ToolCategory.PLATFORM,
    "update_uploaded_skill_file": ToolCategory.PLATFORM,
    "delete_uploaded_skill": ToolCategory.PLATFORM,
    # ── 模型（预留）──
    # ── 浏览器 ──
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
    # ── 文档 ──
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
}


class Layer(StrEnum):
    GLOBAL_ATOMIC = "global_atomic"
    SKILL_RUNTIME = "skill_runtime"
    SKILL = "skill"


class ToolScope(StrEnum):
    """工具可见性范围。

    - ORCHESTRATOR: 所有智能体可见（通用原子工具）
    - SPECIALIST: 仅专精 Agent 可见（自动推导，无需手动维护）
    - ADMIN: 仅管理员可用（需权限检查）
    - INTERNAL: 完全隐藏
    """
    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"
    ADMIN = "admin"
    INTERNAL = "internal"


# --- 全局原子 Tool 校验索引（仅用于 is_global_atomic_tool 门禁）---
GLOBAL_ATOMIC_TOOL_NAMES: frozenset[str] = frozenset(
    {
        *RETRIEVAL_TOOL_NAMES,
        *DOCUMENT_TOOL_NAMES,
        *PLATFORM_TOOL_NAMES,
        *BROWSER_TOOL_NAMES,
        *ADMIN_USER_TOOL_NAMES,
        *ADMIN_DEPT_TOOL_NAMES,
        "read_agent_memory",
        "append_agent_memory",
        "mermaid_diagram",
        "knowledge_folder_search",
        "list_mounted_folders",
    }
)

# Skill 运行时原语 — 单一事实源：ALL_TOOLS.authority 含 skill_runtime
# （定义见 agent_tool_args.SKILL_RUNTIME_TOOL_NAMES）

# 父编排层不可见/不可发现：技能与脚本的直接执行入口（执行交给 use 子智能体）
PARENT_HIDDEN_EXECUTION_ENTRYPOINTS: frozenset[str] = frozenset(
    {
        "invoke_skill",
        "run_skill_script",
        "load_uploaded_skill",
        "create_skill",
        "update_uploaded_skill_file",
        "delete_uploaded_skill",
        "list_agent_skills",
    }
)

SKILL_MGMT_TOOL_NAMES: tuple[str, ...] = (
    "list_agent_skills",
    "load_uploaded_skill",
    "run_skill_script",
    "create_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
)

SKILL_MGMT_OPERATION_ALIASES: dict[str, str] = {
    "list_uploaded_skills": "list_agent_skills",
    "list_skills": "list_agent_skills",
}

NOTIFICATION_TOOL_NAMES: tuple[str, ...] = (
    "send_notification",
    "schedule_notification",
    "list_scheduled_notifications",
    "cancel_scheduled_notification",
)


def normalize_skill_mgmt_operation(operation: str) -> str:
    op = (operation or "").strip()
    return SKILL_MGMT_OPERATION_ALIASES.get(op, op)


def skill_mgmt_operations_hint() -> str:
    return "、".join(SKILL_MGMT_TOOL_NAMES)


# ── 智能体已挂载工具（默认挂载表；可被 DB binding.runtime_tool_names 覆盖）──
# 分层：
#   ALL_TOOLS（平台工具目录，不等于任一 Agent 可见集）
#   → 本表 / binding = 该 Agent「已挂载」工具（LLM 可见上界）
#   → 父编排另隐藏 PARENT_HIDDEN_EXECUTION_ENTRYPOINTS，且非直调工具强制子智能体执行
#   → 专精 Agent：挂载集内可直执（含 invoke_skill 等，视挂载而定）
AGENT_TOOL_WHITELIST: dict[str, dict[str, tuple[str, ...]]] = {
    "orchestrator": {
        "runtime": (
            "find_skills",
            "describe_tool",
            "search_tools",
            "ask_user_choice",
            "invoke_context_subagent",
            "mermaid_diagram",
            "run_tool_batch",
        ),
        "atomic": (
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            ATOMIC_TOOL_KG_QUERY,
            "fetch_url_content",
            "knowledge_folder_search",
            "list_mounted_folders",
            "search_documents_by_name",
            "read_document_content",
            "list_todos",
            "create_todo",
            "update_todo",
            "delete_todo",
            "send_notification",
            "schedule_notification",
            "list_scheduled_notifications",
            "cancel_scheduled_notification",
            "read_agent_memory",
            "append_agent_memory",
            "stock_quote",
            "stock_kline",
            "market_indices",
            "finance_search",
            "carbon_price",
            "carbon_policy",
            "carbon_data",
            *BROWSER_TOOL_NAMES,
        ),
    },
    "platform": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            *DOCUMENT_TOOL_NAMES,
            *PLATFORM_TOOL_NAMES,
            *NOTIFICATION_TOOL_NAMES,
            "read_agent_memory",
            "append_agent_memory",
            *ADMIN_USER_TOOL_NAMES,
            *ADMIN_DEPT_TOOL_NAMES,
        ),
    },
    "skill-dev": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            "list_agent_skills",
            "load_uploaded_skill",
            "run_skill_script",
            "create_skill",
            "update_uploaded_skill_file",
            "delete_uploaded_skill",
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            "fetch_url_content",
            *BROWSER_TOOL_NAMES,
            "read_agent_memory",
            "append_agent_memory",
        ),
    },
    "carbon": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            ATOMIC_TOOL_KG_QUERY,
            "knowledge_folder_search",
            "list_mounted_folders",
            "fetch_url_content",
            "carbon_price",
            "carbon_policy",
            "carbon_data",
            "read_agent_memory",
            "append_agent_memory",
        ),
    },
    "report": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            "fetch_url_content",
            "read_agent_memory",
            "append_agent_memory",
        ),
    },
    "power-economy": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            ATOMIC_TOOL_KG_QUERY,
            "knowledge_folder_search",
            "list_mounted_folders",
            "fetch_url_content",
            "read_agent_memory",
            "append_agent_memory",
        ),
    },
    "stock": {
        "runtime": ("invoke_skill", "find_skills", "invoke_context_subagent", "request_orchestrator_assist"),
        "atomic": (
            ATOMIC_TOOL_WEB_SEARCH,
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            ATOMIC_TOOL_KG_QUERY,
            "knowledge_folder_search",
            "list_mounted_folders",
            "fetch_url_content",
            "read_agent_memory",
            "append_agent_memory",
            # 金融数据
            "stock_quote",
            "stock_kline",
            "market_indices",
            "finance_search",
        ),
    },
}

# 向后兼容：从 AGENT_TOOL_WHITELIST 推导旧 DEFAULT_AGENT_TOOLS 格式
DEFAULT_AGENT_TOOLS: dict[str, tuple[str, ...]] = {
    aid: cfg["runtime"] + cfg["atomic"]
    for aid, cfg in AGENT_TOOL_WHITELIST.items()
}


def skill_runtime_tools_for_agent(agent_id: str) -> frozenset[str]:
    aid = (agent_id or "").strip()
    cfg = AGENT_TOOL_WHITELIST.get(aid)
    if cfg is None:
        return frozenset({"invoke_skill", "request_orchestrator_assist"})
    return frozenset(cfg["runtime"])


def agent_atomic_tool_names(agent_id: str) -> tuple[str, ...]:
    aid = (agent_id or "").strip()
    cfg = AGENT_TOOL_WHITELIST.get(aid)
    return cfg["atomic"] if cfg else ()


# ── 工具可见性范围（唯一源：AGENT_TOOL_WHITELIST） ────────────────
# 工具自动推导规则：
#   - 在 orchestrator 白名单中 → ORCHESTRATOR scope（所有智能体可见）
#   - 不在 orchestrator 白名单但属于某专精 Agent → SPECIALIST scope
#   - ADMIN 工具需额外权限检查（显式声明）

_ADMIN_ONLY_TOOL_NAMES: frozenset[str] = frozenset({
    "list_users", "create_user", "update_user", "delete_user",
    "list_departments", "create_department", "update_department", "delete_department",
})


def _build_tool_scope_from_whitelist() -> dict[str, ToolScope]:
    """从 AGENT_TOOL_WHITELIST 自动推导工具可见性范围。"""
    scope: dict[str, ToolScope] = {}
    for t in _ADMIN_ONLY_TOOL_NAMES:
        scope[t] = ToolScope.ADMIN

    orch_tools: set[str] = set()
    for cat in ("runtime", "atomic"):
        orch_tools.update(AGENT_TOOL_WHITELIST.get("orchestrator", {}).get(cat, ()))

    for aid, cfg in AGENT_TOOL_WHITELIST.items():
        if aid == "orchestrator":
            continue
        for cat in ("runtime", "atomic"):
            for t in cfg.get(cat, ()):
                if t not in orch_tools:
                    scope[t] = ToolScope.SPECIALIST
    return scope


_TOOL_SCOPE: dict[str, ToolScope] = _build_tool_scope_from_whitelist()


def get_tool_scope(name: str) -> ToolScope:
    return _TOOL_SCOPE.get((name or "").strip(), ToolScope.ORCHESTRATOR)


def mounted_tool_names_for_agent(agent_id: str | None) -> frozenset[str]:
    """该智能体默认已挂载工具名（不含 DB binding 动态覆盖；运行时以 specs 为准）。"""
    aid = (agent_id or "").strip() or "orchestrator"
    cfg = AGENT_TOOL_WHITELIST.get(aid)
    if cfg is None:
        return frozenset()
    return frozenset(cfg.get("runtime", ())) | frozenset(cfg.get("atomic", ()))


def is_tool_visible_to_agent(name: str, agent_id: str | None) -> bool:
    """工具是否对某 Agent 可发现（describe_tool）。以已挂载集为准，非平台全库。"""
    n = (name or "").strip()
    scope = get_tool_scope(n)
    if scope == ToolScope.INTERNAL:
        return False
    aid = (agent_id or "").strip().lower() or "orchestrator"
    mounted = mounted_tool_names_for_agent(aid)
    if aid == "orchestrator":
        return n in mounted and n not in PARENT_HIDDEN_EXECUTION_ENTRYPOINTS
    # 专精：挂载集内可见；未入表时回退 scope（兼容旧工具）
    if mounted:
        return n in mounted
    return scope in (ToolScope.ORCHESTRATOR, ToolScope.SPECIALIST, ToolScope.ADMIN)


def skill_id_for_tool(tool_id: str) -> str:
    return (tool_id or "").strip()


def is_global_atomic_tool(name: str) -> bool:
    return (name or "").strip() in GLOBAL_ATOMIC_TOOL_NAMES


def is_skill_runtime_tool(name: str) -> bool:
    return (name or "").strip() in SKILL_RUNTIME_TOOL_NAMES


# --- 内置领域 Skill ---
SKILL_BROWSER_AUTOMATION = "browser-automation"
SKILL_SKILL_DEV = "skill-development"
SKILL_FREE_WEB_AI = "free-web-ai"
SKILL_CARBON_QA = "carbon-qa"
SKILL_STOCK_DEEP_ANALYSIS = "stock-deep-analysis"
SKILL_STOCK_ROUNDTABLE = "stock-roundtable"
SKILL_STOCK_VOLUME_PRICE = "stock-volume-price"

SKILL_DEV_AUXILIARY_SKILLS: tuple[str, ...] = ()


def build_skill_dev_system_access_hint() -> str:
    """skill-dev 系统能力路径提示（注入 prompt）。"""
    return (
        "【skill-dev · 系统能力提示】\n"
        "技能管理工具可直接调用：create_skill、list_agent_skills、load_uploaded_skill、"
        "run_skill_script、update_uploaded_skill_file、delete_uploaded_skill\n"
        "浏览器工具可直接调用：browser_navigate、browser_snapshot、browser_click 等\n"
        "联网检索用 invoke_context_subagent(kind=search, queries=[...]) 委托子 Agent"
    )


# 专精 Agent 默认 Skill 绑定（仅用于倒排索引）
# 技能是动态挂载的，此处仅声明内置默认绑定
AGENT_DEFAULT_SKILLS: dict[str, tuple[str, ...]] = {
    "skill-dev": (SKILL_SKILL_DEV,),
    "carbon": (SKILL_CARBON_QA,),
    "stock": (
        SKILL_STOCK_DEEP_ANALYSIS,
        SKILL_STOCK_ROUNDTABLE,
        SKILL_STOCK_VOLUME_PRICE,
    ),
}

# 内置系统 Skill 名称集合
BUILTIN_SKILL_NAMES: frozenset[str] = frozenset({
    SKILL_FREE_WEB_AI,
    SKILL_CARBON_QA,
    SKILL_STOCK_DEEP_ANALYSIS,
    SKILL_STOCK_ROUNDTABLE,
    SKILL_STOCK_VOLUME_PRICE,
})

# 检索类 Skill → 内部原子 Tool
RETRIEVAL_SKILL_ATOMIC_MAP: dict[str, tuple[str, str]] = {}


