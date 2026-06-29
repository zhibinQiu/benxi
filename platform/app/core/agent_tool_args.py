"""Agent 工具参数 Pydantic 模型 — 运行时强校验 + 紧凑 JSON Schema（全量工具）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


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


class RunToolBatchStepArgs(_StrictArgs):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class RunToolBatchArgs(_StrictArgs):
    steps: list[RunToolBatchStepArgs] = Field(min_length=1, max_length=6)


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


# --- 浏览器 ---


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
    delay_minutes: int | None = Field(default=None, ge=1, le=525600)
    scheduled_at: str | None = Field(default=None, max_length=64)


# --- 文档库 ---


class SearchDocumentsByNameArgs(_StrictArgs):
    name: str = Field(min_length=1, max_length=200)
    scope: DocumentScope | None = None
    limit: int = Field(default=20, ge=1, le=50)


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
    delay_minutes: int | None = Field(default=None, ge=1, le=525600)
    delay_seconds: int | None = Field(default=None, ge=1, le=31536000)
    scheduled_at: str | None = Field(default=None, max_length=64)


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
    ATOMIC_TOOL_WEB_SEARCH: ("联网检索公开信息；简单查价/新闻优先此工具", WebSearchArgs),
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: ("检索企业文档库", KnowledgeRetrieveArgs),
    ATOMIC_TOOL_KG_QUERY: ("查询本体图谱", KgQueryArgs),
    "search_tools": ("按关键词搜索可用工具", SearchToolsArgs),
    "run_tool_batch": ("批量执行只读/检索工具", RunToolBatchArgs),
    "load_uploaded_skill": ("加载上传 Skill 的 SKILL.md", LoadUploadedSkillArgs),
    "run_skill_script": (
        "执行含 main.py 的发展 Skill；entry 填 .py 路径或留空，勿填 cat 等 shell 命令",
        RunSkillScriptArgs,
    ),
    "create_uploaded_skill": ("创建上传型 Skill（含 SKILL.md 与脚本）", CreateUploadedSkillArgs),
    "update_uploaded_skill_file": ("更新 Skill 文本文件", UpdateUploadedSkillFileArgs),
    "delete_uploaded_skill": ("删除上传型 Skill", DeleteUploadedSkillArgs),
    "list_agent_skills": ("列出平台 Skills 目录（匹配已有技能）", ListAgentSkillsArgs),
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

AGENT_SKILL_TOOL_NAMES: tuple[str, ...] = (
    "load_uploaded_skill",
    "create_uploaded_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
    "list_agent_skills",
    "read_agent_memory",
    "append_agent_memory",
)

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


def _compact_schema(schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties")
    if isinstance(props, dict):
        for spec in props.values():
            if isinstance(spec, dict):
                spec.pop("title", None)
                spec.pop("description", None)
    out: dict[str, Any] = {
        "type": "object",
        "properties": props or {},
    }
    required = schema.get("required")
    if required:
        out["required"] = required
    defs = schema.get("$defs")
    if defs:
        for item in defs.values():
            if isinstance(item, dict) and "properties" in item:
                for spec in item["properties"].values():
                    if isinstance(spec, dict):
                        spec.pop("title", None)
                        spec.pop("description", None)
        out["$defs"] = defs
    return out


def tool_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    return _compact_schema(schema)


def build_function_tool_spec(
    *,
    name: str,
    description: str,
    args_model: type[BaseModel],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": tool_parameters_schema(args_model),
        },
    }


def build_tool_specs(names: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in names:
        desc, model = TOOL_DEFINITIONS[name]
        specs.append(
            build_function_tool_spec(name=name, description=desc, args_model=model)
        )
    return specs


def format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:4]:
        loc = ".".join(str(x) for x in err.get("loc") or ())
        msg = str(err.get("msg") or "无效")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "参数无效：" + "；".join(parts)


def validate_tool_arguments(
    tool_name: str,
    raw: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
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
