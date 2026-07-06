"""Agent 工具参数 Pydantic 模型 — 运行时强校验 + 紧凑 JSON Schema（全量工具）。"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from agentkit_tools.schema import build_function_tool_spec as _build_function_tool_spec
from agentkit_tools.validate import format_validation_error as _format_validation_error

from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)

DocumentScope = Literal["personal", "company", "department", "team"]
ShareLevel = Literal["visible", "query", "modify"]
TodoStatus = Literal["pending", "done"]
ContentFormat = Literal["markdown", "plain"]


class _StrictArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _coerce_dict_field(value: object) -> dict[str, Any]:
    """LLM 常将 dict 参数序列化为 JSON 字符串；统一归一化为 dict。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class EmptyArgs(_StrictArgs):
    pass


# --- 检索 ---


class WebSearchArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    max_items: int = Field(default=8, ge=1, le=20)


class KnowledgeRetrieveArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    doc_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=8, ge=1, le=30)


class KgQueryArgs(_StrictArgs):
    question: str = Field(min_length=1, max_length=500)


class SearchToolsArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=15)


class InvokeSkillArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120, description="Skill slug")
    action: str = Field(min_length=1, max_length=80, description="Skill 内 action/tool 名")
    params: dict[str, Any] = Field(default_factory=dict, description="传给 Skill action 的参数")

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, value: object) -> dict[str, Any]:
        return _coerce_dict_field(value)


class DomainSkillCallArgs(_StrictArgs):
    operation: str = Field(min_length=1, max_length=80, description="底层原子 Tool 名")
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, value: object) -> dict[str, Any]:
        return _coerce_dict_field(value)


class SearchSkillsArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=15)


class RunToolBatchStepArgs(_StrictArgs):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments", mode="before")
    @classmethod
    def _coerce_arguments(cls, value: object) -> dict[str, Any]:
        return _coerce_dict_field(value)


class RunToolBatchArgs(_StrictArgs):
    steps: list[RunToolBatchStepArgs] = Field(min_length=1, max_length=6)


ContextSubagentKind = Literal["explore", "browser_digest"]


class InvokeContextSubagentArgs(_StrictArgs):
    kind: ContextSubagentKind = Field(
        description=(
            "explore=子 Agent 调用 web-search/knowledge-search/kg-palantir 多源检索；"
            "browser_digest=子 Agent 调用 browser-automation 取证页面（浏览器未开启时自动 explore）"
        )
    )
    task: str = Field(default="", max_length=1200, description="单子任务描述")
    queries: list[str] | None = Field(
        default=None,
        max_length=4,
        description="explore 专用：2–4 个 query 并行检索（省 token，优于多次调用）",
    )

    @field_validator("queries", mode="before")
    @classmethod
    def _normalize_queries(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return None
        return [str(x).strip() for x in value if str(x).strip()]

    @model_validator(mode="after")
    def _task_or_queries(self) -> InvokeContextSubagentArgs:
        if (self.task or "").strip() or (self.queries or []):
            return self
        raise ValueError("task 与 queries 至少填一项")


# --- Skill / 记忆 ---


class LoadUploadedSkillArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)


class RunSkillScriptArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)
    entry: str | None = Field(
        default=None,
        max_length=120,
        description="Python 入口相对路径（如 main.py）；勿填 shell 命令；留空自动选择",
    )
    args: list[str] | None = Field(default=None, max_length=20)


class CreateUploadedSkillArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    skill_md_body: str = Field(min_length=1, max_length=50000)
    extra_files: dict[str, str] | None = None
    replace_existing: bool = False

    @field_validator("extra_files", mode="before")
    @classmethod
    def _coerce_extra_files(cls, value: object) -> dict[str, str] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            out = {str(k).strip(): str(v) for k, v in value.items() if str(k).strip()}
            return out or None
        if isinstance(value, str):
            coerced = _coerce_dict_field(value)
            out = {str(k).strip(): str(v) for k, v in coerced.items() if str(k).strip()}
            return out or None
        if isinstance(value, list):
            out: dict[str, str] = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or item.get("file_path") or "").strip()
                if path:
                    out[path] = str(item.get("content") or "")
            return out or None
        return None


class UpdateUploadedSkillFileArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)
    file_path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=200000)


class DeleteUploadedSkillArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)


class ListAgentSkillsArgs(_StrictArgs):
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=40, ge=1, le=80)
    uploaded_only: bool = True


class AppendAgentMemoryArgs(_StrictArgs):
    note: str = Field(min_length=1, max_length=2000)


class RequestOrchestratorAssistArgs(_StrictArgs):
    reason: str = Field(
        min_length=1,
        max_length=2000,
        description="无法在本域完成的原因（调度层据此路由其他智能体）",
    )
    needed_from: str = Field(
        min_length=1,
        max_length=500,
        description="需要哪类能力/哪类专精协助（如：知识库检索、文档库操作）",
    )
    suggested_agent_id: str | None = Field(
        default=None,
        max_length=40,
        description="建议调度的专精 id（可选）：platform/research/skill-dev 等",
    )


# --- 浏览器 ---


class AskUserChoiceArgs(_StrictArgs):
    question: str = Field(min_length=1, max_length=1000, description="向用户提出的问题，清晰描述需要用户做选择的场景")
    options: list[str] = Field(min_length=2, max_length=6, description="供用户选择的选项列表（2-6 个），每个选项简洁明了")

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options(cls, value: object) -> list[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
            return [value]
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return []


class BrowserNavigateArgs(_StrictArgs):
    url: str = Field(min_length=8, max_length=2000)


class BrowserClickArgs(_StrictArgs):
    ref: str = Field(min_length=1, max_length=40)


class BrowserTypeArgs(_StrictArgs):
    ref: str = Field(min_length=1, max_length=40)
    text: str = Field(max_length=4000)
    submit: bool = False


class BrowserFillFieldArgs(_StrictArgs):
    ref: str = Field(min_length=1, max_length=40)
    value: str = Field(max_length=4000)


class BrowserFillArgs(_StrictArgs):
    fields: list[BrowserFillFieldArgs] = Field(min_length=1, max_length=30)


class BrowserScreenshotArgs(_StrictArgs):
    full_page: bool = False


class BrowserSaveWorkflowArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    parameters: list[str] | None = Field(default=None, max_length=20)
    replace_existing: bool = True


class BrowserReplayWorkflowArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)
    parameters: dict[str, str] | None = None


class BrowserRunTaskArgs(_StrictArgs):
    task: str = Field(min_length=1, max_length=2000)
    start_url: str | None = Field(default=None, max_length=2000)
    max_steps: int | None = Field(default=None, ge=1, le=40)


class ScheduleBrowserWorkflowArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120)
    parameters: dict[str, str] | None = None
    scheduled_at: str = Field(min_length=1, max_length=64, description="ISO 8601 绝对时间，如 2026-07-06T12:00:00+08:00")


# --- 文档库 ---


class SearchDocumentsByNameArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=200)
    scope: DocumentScope | None = None
    limit: int = Field(default=20, ge=1, le=50)


class ReadDocumentContentArgs(_StrictArgs):
    document_id: str | None = Field(default=None, max_length=64)
    document_name: str | None = Field(default=None, max_length=200)
    max_chars: int = Field(default=16000, ge=500, le=80000)


class ListLibraryDocumentsArgs(_StrictArgs):
    scope: DocumentScope = "personal"
    folder_name: str | None = Field(default=None, max_length=200)
    folder_id: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=30, ge=1, le=100)


class ListManageableDocumentsArgs(_StrictArgs):
    keyword: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class ListDocumentFoldersArgs(_StrictArgs):
    scope: DocumentScope


class CreateKbFolderArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=200)
    scope: DocumentScope
    description: str | None = Field(default=None, max_length=500)


class CreateLibraryDocumentArgs(_StrictArgs):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=500000)
    scope: DocumentScope = "personal"
    folder_id: str | None = Field(default=None, max_length=64)
    folder_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    content_format: ContentFormat = "markdown"


class RenameDocumentArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)
    new_title: str = Field(min_length=1, max_length=300)


class MoveDocumentArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)
    folder_id: str | None = Field(default=None, max_length=64)
    folder_name: str | None = Field(default=None, max_length=200)


class ShareDocumentArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)
    user_names: list[str] = Field(min_length=1, max_length=20)
    level: ShareLevel = "query"


class DeleteDocumentArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)
    confirm: bool


class UpdateKbFolderArgs(_StrictArgs):
    scope: DocumentScope = "personal"
    folder_id: str | None = Field(default=None, max_length=64)
    folder_name: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class DeleteKbFolderArgs(_StrictArgs):
    confirm: bool
    scope: DocumentScope = "personal"
    folder_id: str | None = Field(default=None, max_length=64)
    folder_name: str | None = Field(default=None, max_length=200)


class SyncDocumentKnowledgeArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)


class ReindexDocumentArgs(_StrictArgs):
    document_id: str = Field(min_length=1, max_length=64)
    parser_id: str | None = Field(default=None, max_length=80)
    resync: bool = False


# --- 平台 ---


class ListTodosArgs(_StrictArgs):
    status: TodoStatus | None = None


class CreateTodoArgs(_StrictArgs):
    title: str = Field(min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=2000)


class UpdateTodoArgs(_StrictArgs):
    todo_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)
    status: TodoStatus | None = None


class DeleteTodoArgs(_StrictArgs):
    todo_id: str = Field(min_length=1, max_length=64)


class SendNotificationArgs(_StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    link: str | None = Field(default=None, max_length=500)


class ScheduleNotificationArgs(_StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    link: str | None = Field(default=None, max_length=500)
    scheduled_at: str = Field(min_length=1, max_length=64, description="ISO 8601 绝对时间，如 2026-07-06T12:00:00+08:00")


class ListScheduledNotificationsArgs(_StrictArgs):
    limit: int = Field(default=20, ge=1, le=100)


class CancelScheduledNotificationArgs(_StrictArgs):
    notification_id: str = Field(min_length=1, max_length=64)


# --- 管理 ---


class ListUsersArgs(_StrictArgs):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=200)


class CreateUserArgs(_StrictArgs):
    phone: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=3, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    status: str = Field(default="active", max_length=32)
    department_id: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=200)


class UpdateUserArgs(_StrictArgs):
    user_id: str | None = Field(default=None, max_length=64)
    user_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    department_id: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=200)
    clear_department: bool = False


class DeleteUserArgs(_StrictArgs):
    confirm: bool
    user_id: str | None = Field(default=None, max_length=64)
    user_name: str | None = Field(default=None, max_length=200)


class CreateDepartmentArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, max_length=64)
    parent_name: str | None = Field(default=None, max_length=200)


class UpdateDepartmentArgs(_StrictArgs):
    department_id: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    parent_id: str | None = Field(default=None, max_length=64)
    parent_name: str | None = Field(default=None, max_length=200)
    clear_parent: bool = False


class DeleteDepartmentArgs(_StrictArgs):
    confirm: bool
    department_id: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=200)


# 工具名 -> (短描述, 参数模型)
TOOL_DEFINITIONS: dict[str, tuple[str, type[BaseModel]]] = {
    ATOMIC_TOOL_WEB_SEARCH: ("联网检索公开信息；简单公开信息/新闻优先此工具", WebSearchArgs),
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: ("检索企业文档库", KnowledgeRetrieveArgs),
    ATOMIC_TOOL_KG_QUERY: ("查询本体图谱", KgQueryArgs),
    "invoke_skill": (
        "调用已绑定 Skill：检索/文档库/技能开发等经此入口。"
        "文档库 invoke_skill(document-library, call, {operation, params})；"
        "技能开发 invoke_skill(skill-development, call, {operation: create_skill, ...})",
        InvokeSkillArgs,
    ),
    "search_skills": ("按关键词搜索可用 Skill 路由", SearchSkillsArgs),
    "search_tools": ("【内部】按关键词搜索原子工具；优先使用 search_skills", SearchToolsArgs),
    "run_tool_batch": ("批量执行只读/检索工具", RunToolBatchArgs),
    "invoke_context_subagent": (
        "委托子 Agent 调用系统 Skill：browser_digest→browser-automation 页面取证；"
        "explore→web-search/knowledge-search/kg-palantir 并行检索。"
        "skill-dev 创建 Skill 时的纯主题检索（无浏览器操作）走本工具",
        InvokeContextSubagentArgs,
    ),
    "load_uploaded_skill": ("加载上传 Skill 的 SKILL.md", LoadUploadedSkillArgs),
    "run_skill_script": (
        "执行含 main.py 的发展 Skill；entry 填 .py 路径或留空，勿填 cat 等 shell 命令。"
        "入口须 `import skill_runtime`（否则 NameError），结论用 skill_runtime.finish",
        RunSkillScriptArgs,
    ),
    "create_skill": (
        "创建上传型 Skill：name 为英文 slug（carbon-market-price）；"
        "数据/抓取类 extra_files 须含 main.py（import skill_runtime + skill_runtime.finish + fetch_text，"
        "禁 requests/open/subprocess）",
        CreateUploadedSkillArgs,
    ),
    "update_uploaded_skill_file": (
        "更新 Skill 文本文件；更新 .py 文件时内容顶部必须 `import skill_runtime`"
        "（否则执行报 NameError），结论用 skill_runtime.finish",
        UpdateUploadedSkillFileArgs,
    ),
    "delete_uploaded_skill": ("删除上传型 Skill", DeleteUploadedSkillArgs),
    "list_agent_skills": ("列出平台 Skills 目录（非创建流程；生成 Skill 时勿调用）", ListAgentSkillsArgs),
    "read_agent_memory": ("读取用户 MEMORY.md", EmptyArgs),
    "append_agent_memory": ("追加用户记忆", AppendAgentMemoryArgs),
    "browser_navigate": ("打开 http/https 页面", BrowserNavigateArgs),
    "browser_snapshot": ("获取页面可交互元素 ref", EmptyArgs),
    "browser_click": ("点击 ref 元素", BrowserClickArgs),
    "browser_type": ("向 ref 输入框填文本", BrowserTypeArgs),
    "browser_fill": ("批量填表", BrowserFillArgs),
    "browser_screenshot": ("截取当前页面", BrowserScreenshotArgs),
    "browser_save_workflow": ("保存浏览器录制为 RPA Skill", BrowserSaveWorkflowArgs),
    "browser_close_session": ("关闭浏览器会话", EmptyArgs),
    "browser_replay_workflow": ("回放 RPA Skill", BrowserReplayWorkflowArgs),
    "browser_run_task": ("自然语言驱动浏览器任务", BrowserRunTaskArgs),
    "schedule_browser_workflow": ("定时回放 RPA Skill", ScheduleBrowserWorkflowArgs),
    "search_documents_by_name": ("按文档标题关键词搜索并列出可见文档", SearchDocumentsByNameArgs),
    "read_document_content": (
        "读取平台文档库指定文档的解析正文（当前版本，支持按 document_id 或 document_name）",
        ReadDocumentContentArgs,
    ),
    "list_library_documents": ("列出文档库文档", ListLibraryDocumentsArgs),
    "list_manageable_documents": ("列出可管理文档", ListManageableDocumentsArgs),
    "list_document_folders": ("列出文档库文件夹", ListDocumentFoldersArgs),
    "create_kb_folder": ("新建文档库文件夹", CreateKbFolderArgs),
    "create_library_document": ("写入文档库", CreateLibraryDocumentArgs),
    "rename_document": ("重命名文档", RenameDocumentArgs),
    "move_document": ("移动文档", MoveDocumentArgs),
    "share_document": ("分享文档", ShareDocumentArgs),
    "delete_document": ("删除文档（须 confirm）", DeleteDocumentArgs),
    "update_kb_folder": ("更新文件夹", UpdateKbFolderArgs),
    "delete_kb_folder": ("删除文件夹（须 confirm）", DeleteKbFolderArgs),
    "sync_document_knowledge": ("同步文档到知识库", SyncDocumentKnowledgeArgs),
    "reindex_document": ("重建文档索引", ReindexDocumentArgs),
    "list_todos": ("列出待办", ListTodosArgs),
    "create_todo": ("创建待办", CreateTodoArgs),
    "update_todo": ("更新待办", UpdateTodoArgs),
    "delete_todo": ("删除待办", DeleteTodoArgs),
    "send_notification": ("立即发送系统通知", SendNotificationArgs),
    "schedule_notification": ("定时发送通知", ScheduleNotificationArgs),
    "list_scheduled_notifications": ("列出定时通知", ListScheduledNotificationsArgs),
    "cancel_scheduled_notification": ("取消定时通知", CancelScheduledNotificationArgs),
    "ask_user_choice": (
        "向用户提出方案选择，让用户从多个选项中挑选一个再继续执行。"
        "当已有信息不足以做单一决策、存在多种合理方案、或用户偏好会影响结果时，"
        "必须使用此工具询问用户，不要替用户做不确定的猜测。"
        "适用场景举例：导出格式（PDF/Word/Markdown）、分析时间范围、"
        "报告风格偏好、多种数据可视化方案、多个执行路径等。"
        "question 参数清晰描述需要用户决定什么，"
        "options 参数列出 2-6 个简洁明了的选项供用户选择。",
        AskUserChoiceArgs,
    ),
    "request_orchestrator_assist": (
        "本域无法完成时向调度智能体反馈，由调度层协调其他专精协助后再交还你续办",
        RequestOrchestratorAssistArgs,
    ),
    "list_users": ("列出用户", ListUsersArgs),
    "create_user": ("创建用户", CreateUserArgs),
    "update_user": ("更新用户", UpdateUserArgs),
    "delete_user": ("删除用户（须 confirm）", DeleteUserArgs),
    "list_departments": ("列出部门", EmptyArgs),
    "create_department": ("创建部门", CreateDepartmentArgs),
    "update_department": ("更新部门", UpdateDepartmentArgs),
    "delete_department": ("删除部门（须 confirm）", DeleteDepartmentArgs),
}

TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    name: model for name, (_, model) in TOOL_DEFINITIONS.items()
}

RETRIEVAL_TOOL_NAMES: tuple[str, ...] = (
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_KG_QUERY,
)

BROWSER_TOOL_NAMES: tuple[str, ...] = tuple(
    name for name in TOOL_DEFINITIONS if name.startswith("browser_") or name == "schedule_browser_workflow"
)

DOCUMENT_TOOL_NAMES: tuple[str, ...] = (
    "search_documents_by_name",
    "read_document_content",
    "list_library_documents",
    "list_manageable_documents",
    "list_document_folders",
    "create_kb_folder",
    "create_library_document",
    "rename_document",
    "move_document",
    "share_document",
    "delete_document",
    "update_kb_folder",
    "delete_kb_folder",
    "sync_document_knowledge",
    "reindex_document",
)

ORCHESTRATION_TOOL_NAMES: tuple[str, ...] = (
    "request_orchestrator_assist",
    "invoke_context_subagent",
)

PLATFORM_TOOL_NAMES: tuple[str, ...] = (
    "list_todos",
    "create_todo",
    "update_todo",
    "delete_todo",
    "send_notification",
    "schedule_notification",
    "list_scheduled_notifications",
    "cancel_scheduled_notification",
)

SKILL_RUNTIME_TOOL_NAMES: tuple[str, ...] = (
    "invoke_skill",
    "search_skills",
    "load_uploaded_skill",
    "create_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
    "list_agent_skills",
)

# 记忆由系统自动处理；原子读写仅在内部 Tool 池
AGENT_SKILL_TOOL_NAMES: tuple[str, ...] = SKILL_RUNTIME_TOOL_NAMES

ADMIN_USER_TOOL_NAMES: tuple[str, ...] = (
    "list_users",
    "create_user",
    "update_user",
    "delete_user",
)

ADMIN_DEPT_TOOL_NAMES: tuple[str, ...] = (
    "list_departments",
    "create_department",
    "update_department",
    "delete_department",
)


def build_tool_specs(names: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    """批量构建 OpenAI function calling spec（基于平台 TOOL_DEFINITIONS）。"""
    specs: list[dict[str, Any]] = []
    for name in names:
        desc, model = TOOL_DEFINITIONS[name]
        specs.append(
            _build_function_tool_spec(name=name, description=desc, args_model=model)
        )
    return specs


def format_validation_error(exc: ValidationError) -> str:
    """将 Pydantic ValidationError 格式化为 LLM 友好的错误消息。"""
    return _format_validation_error(exc)


def validate_tool_arguments(
    tool_name: str,
    raw: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """校验工具参数：查注册表 → Pydantic 校验 → 返回清理后 dict。"""
    name = (tool_name or "").strip()
    model_cls = TOOL_ARG_MODELS.get(name)
    payload = dict(raw or {})
    if model_cls is None:
        return None, f"未注册工具参数模型: {name}"
    try:
        model = model_cls.model_validate(payload)
        return model.model_dump(exclude_none=True), None
    except ValidationError as exc:
        return None, format_validation_error(exc)
