"""Agent 工具参数 Pydantic 模型 — 运行时强校验 + 紧凑 JSON Schema（全量工具）。"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from app.agentkit.tools.schema import build_function_tool_spec as _build_function_tool_spec
from app.agentkit.tools.schema import compact_tool_parameters_schema as tool_parameters_schema
from app.agentkit.tools.validate import (
    coerce_dict_field,
    format_validation_error as _format_validation_error,
)

# 公开别名，供 agent_tool_search 等模块导入
build_function_tool_spec = _build_function_tool_spec

from app.core.tool_def_loader import get_tool_description
from app.services.skill_chat_service import (
    ATOMIC_TOOL_FETCH_URL_CONTENT,
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_ONTOLOGY_QUERY,
)

DocumentScope = Literal["personal", "company", "department", "team"]
ShareLevel = Literal["visible", "query", "modify"]
TodoStatus = Literal["pending", "done"]
ContentFormat = Literal["markdown", "plain"]


class _StrictArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class EmptyArgs(_StrictArgs):
    pass


# --- 检索 ---


class WebSearchArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    max_items: int = Field(default=8, ge=1, le=20)
    read_full: int = Field(
        default=3, ge=0, le=6,
        description="读取前 N 条链接的全文（Markdown），0=仅返回搜索引擎摘要",
    )


class KnowledgeRetrieveArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    doc_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=8, ge=1, le=30)


class KnowledgeFolderSearchArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=30)


class EmptyMountedFoldersArgs(_StrictArgs):
    pass


class KgQueryArgs(_StrictArgs):
    question: str = Field(min_length=1, max_length=500)


class MermaidDiagramArgs(_StrictArgs):
    description: str = Field(min_length=1, max_length=1000, description="图表类型和内容描述")


class SearchToolsArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=15)


class StockQuoteArgs(_StrictArgs):
    codes: str = Field(description="股票代码，逗号分隔多个，如 600519,000001。支持上海 sh6/s h68、深圳 sz0/sz3 格式。")


class StockKlineArgs(_StrictArgs):
    code: str = Field(min_length=4, max_length=10, description="股票代码，如 600519、000001")
    ktype: str = Field(default="day", description="K 线类型: day(日K) / week(周K) / month(月K)")


class MarketIndicesArgs(_StrictArgs):
    pass


class FinanceSearchArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=100, description="搜索关键词，股票名或代码")
    market: str = Field(default="stock", description="市场类型: stock(股票) / fund(基金)")


class F10DataArgs(_StrictArgs):
    code: str = Field(min_length=4, max_length=10, description="股票代码，如 000682、600519")
    target_date: str = Field(default="", description="估值截止日期，格式 2026-07-17，留空用当天")
    start_range: str = Field(default="", description="区间涨跌幅起始，格式 2026-06-29，留空默认 15 天前")
    end_range: str = Field(default="", description="区间涨跌幅结束，格式 2026-07-17，留空用当天")
    keywords: str = Field(default="", description="互动易关键词筛选，逗号分隔，如 储能,虚拟电厂,电表")


class CarbonPriceArgs(_StrictArgs):
    keyword: str = Field(default="", description="可选关键词，如 全国碳市场、CCER、广东试点")
    url: str = Field(default="", description="可选，指定官方 URL 直接抓取；留空则按默认碳价源查询")


class CarbonPolicyArgs(_StrictArgs):
    keyword: str = Field(default="", description="可选关键词，如 钢铁纳入碳市场、碳达峰方案")
    url: str = Field(default="", description="可选，指定政策页 URL；留空则按 gov/ndrc/mee/miit 等默认源查询")


class CarbonDataArgs(_StrictArgs):
    topic: str = Field(
        description="数据主题: emission(排放) / ccer / international(国际碳市场) / local(地方双碳方案)",
    )
    keyword: str = Field(default="", description="可选关键词，缩小摘要关注点")
    url: str = Field(default="", description="可选，指定 URL 直接抓取")


class InvokeSkillArgs(_StrictArgs):
    skill_name: str = Field(min_length=1, max_length=120, description="Skill slug")
    action: str = Field(min_length=1, max_length=80, description="Skill 内 action/tool 名")
    params: dict[str, Any] = Field(default_factory=dict, description="传给 Skill action 的参数")

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, value: object) -> dict[str, Any]:
        return coerce_dict_field(value)


class DomainSkillCallArgs(_StrictArgs):
    operation: str = Field(min_length=1, max_length=80, description="底层原子 Tool 名")
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, value: object) -> dict[str, Any]:
        return coerce_dict_field(value)


class FindSkillsArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=15)


class RunToolBatchStepArgs(_StrictArgs):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments", mode="before")
    @classmethod
    def _coerce_arguments(cls, value: object) -> dict[str, Any]:
        return coerce_dict_field(value)


class RunToolBatchArgs(_StrictArgs):
    steps: list[RunToolBatchStepArgs] = Field(min_length=1, max_length=6)


# ── 编排步骤（供 execute 子Agent使用） ──────────────────────


class ExecuteStepItem(_StrictArgs):
    """execute 子Agent 的单个执行步骤。"""
    tool: str = Field(min_length=1, max_length=80, description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    tool_call_id: str = Field(default="", max_length=64, description="父Agent的 tool_call_id，用于关联结果")


ContextSubagentKind = Literal["use", "search", "execute"]


class InvokeContextSubagentArgs(_StrictArgs):
    kind: ContextSubagentKind = Field(
        description=(
            "search=多源检索（文档+联网+本体+图谱）——子 Agent 自主分析意图，"
            "调用 web_search / knowledge_retrieve / kg_query 等多源检索工具；"
            "传入 queries 参数时并行检索多个关键词。"
            "use=执行指定技能——子 Agent 调用 invoke_skill 完成具体技能任务。"
            "execute=执行父智能体编排的步骤——子 Agent 严格按 steps 数组依次执行，"
            "不经过 LLM 决策，直接返回每步的执行结果。"
        )
    )
    task: str = Field(default="", max_length=1200, description="任务描述（search/use 用）")
    queries: list[str] | None = Field(
        default=None,
        max_length=4,
        description="search 可选：2–4 个关键词并行检索；不传则子 Agent 自主分析意图并生成搜索词",
    )
    steps: list[ExecuteStepItem] | None = Field(
        default=None,
        max_length=12,
        description="execute 专用：父智能体编排的步骤列表。子 Agent 严格按顺序执行，不自主决策",
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
    def _task_or_queries_or_steps(self) -> InvokeContextSubagentArgs:
        if (self.task or "").strip() or (self.queries or []) or (self.steps or []):
            return self
        raise ValueError("task、queries 与 steps 至少填一项")


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
            coerced = coerce_dict_field(value)
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


class FetchUrlContentArgs(_StrictArgs):
    url: str = Field(min_length=8, max_length=4000, description="要获取内容的网页 URL（http/https）")
    max_chars: int = Field(default=50000, ge=1000, le=200000, description="最大返回字符数")


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
    title: str = Field(
        min_length=1, max_length=200,
        description="通知标题，简短概括提醒内容。必填，最长 200 字符。"
    )
    body: str | None = Field(
        default=None, max_length=4000,
        description="通知正文（可选）。补充说明提醒详情，最长 4000 字符。不需要时留空。"
    )
    link: str | None = Field(
        default=None, max_length=500,
        description="点击通知后跳转的链接（可选）。如文档/页面 URL。不需要时留空。"
    )


class ScheduleNotificationArgs(_StrictArgs):
    title: str = Field(
        min_length=1, max_length=200,
        description="通知标题，简短概括提醒内容。必填，最长 200 字符。"
    )
    body: str | None = Field(
        default=None, max_length=4000,
        description="通知正文（可选）。补充说明提醒详情，最长 4000 字符。不需要时留空。"
    )
    link: str | None = Field(
        default=None, max_length=500,
        description="点击通知后跳转的链接（可选）。不需要时留空。"
    )
    scheduled_at: str = Field(
        min_length=1, max_length=64,
        description="ISO 8601 绝对时间（含时区），如 2026-07-09T09:30:00+08:00；"
        "或相对时间表达式，如 8s（8秒后）、5分钟、2小时、1天。"
        "推荐直接用相对时间表达式（系统自动换算），更准确可靠。"
    )


class ListScheduledNotificationsArgs(_StrictArgs):
    limit: int = Field(default=20, ge=1, le=100)


class CancelScheduledNotificationArgs(_StrictArgs):
    notification_id: str = Field(min_length=1, max_length=64)


class DescribeToolArgs(_StrictArgs):
    name: str = Field(
        min_length=1, max_length=64,
        description="工具名称，如 web_search、create_document 等",
    )


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


class ToolDef(BaseModel):
    """LangGraph 风格的工具定义：name + description + args_schema + authority 自包含。

    authority 字段替代外部 ``*_TOOL_NAMES`` 常量分组，
    所有 ``*_TOOL_NAMES`` 均由 ``ALL_TOOLS`` 按 authority 自动派生。
    """
    name: str
    description: str
    args_schema: type[BaseModel]
    authority: tuple[str, ...] = ()


# 单一名单 —— 所有工具的唯一来源
# authority 取值：
#   retrieval     → RETRIEVAL_TOOL_NAMES
#   browser       → BROWSER_TOOL_NAMES
#   document      → DOCUMENT_TOOL_NAMES
#   platform      → PLATFORM_TOOL_NAMES
#   orchestration → ORCHESTRATION_TOOL_NAMES
#   admin_user    → ADMIN_USER_TOOL_NAMES
#   admin_dept    → ADMIN_DEPT_TOOL_NAMES
#   skill_runtime → SKILL_RUNTIME_TOOL_NAMES
#   （空）         → 不由 TOOL_NAMES 自动收录（通过 describe_tool 动态解锁）
ALL_TOOLS: list[ToolDef] = [
    # ── 检索 ────────────────────────────────────────────
    ToolDef(
        name=ATOMIC_TOOL_WEB_SEARCH,
        description=(
            "联网检索公开信息，返回各来源全文（Markdown）。"
            "可多次调用此工具实现多轮搜索：先宽泛搜索了解概貌，"
            "根据已读全文生成更具体的关键词继续深挖，"
            "不同来源结论矛盾时追加搜索做交叉验证。"
            "read_full=0 仅返回摘要片段（省 Token），默认 3 条全文。"
        ),
        args_schema=WebSearchArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name=ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        description=(
            "检索企业文档库，返回与 query 相关的文档片段。"
            "当用户问企业知识、文档内容时使用。"
            "返回匹配文档的标题、片段及来源。"
            "⚠ 仅检索已索引到知识库的文档内容，不检索外部网络。"
            "如需搜索公开网络信息请用 web_search。"
        ),
        args_schema=KnowledgeRetrieveArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name=ATOMIC_TOOL_KG_QUERY,
        description=(
            "查询本体知识图谱，返回结构化实体关系。"
            "当用户问实体关系、分类归属、属性信息时使用。"
            "返回匹配的实体、关系及属性。"
            "⚠ 仅查询图谱数据，不检索文档全文。"
            "如需文档内容检索请用 knowledge_retrieve。"
        ),
        args_schema=KgQueryArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="knowledge_folder_search",
        description=(
            "在已挂载的知识库文件夹中检索文档。"
            "仅检索 Agent 已挂载文件夹内的文档内容。"
            "若未挂载任何文件夹则返回空结果。"
        ),
        args_schema=KnowledgeFolderSearchArgs,
        authority=("knowledge_folder",),
    ),
    ToolDef(
        name="list_mounted_folders",
        description="列出当前 Agent 已挂载的知识库文件夹信息。",
        args_schema=EmptyMountedFoldersArgs,
        authority=("knowledge_folder",),
    ),
    # ── 金融数据 ──────────────────────────────────────────
    ToolDef(
        name="stock_quote",
        description=(
            "获取中国 A 股实时行情数据。返回最新价、涨跌幅、涨跌额、"
            "最高价、最低价、成交量、成交额、市盈率、振幅等常用指标。"
            "可一次查询多只股票（逗号分隔）。"
        ),
        args_schema=StockQuoteArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="stock_kline",
        description=(
            "获取中国 A 股历史 K 线数据，用于技术面分析。"
            "支持日 K、周 K、月 K 三种周期，返回 OHLC（开/高/低/收）和成交量。"
        ),
        args_schema=StockKlineArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="market_indices",
        description=(
            "获取中国 A 股主要市场指数实时行情，包括：上证指数、深证成指、"
            "创业板指、科创 50、沪深 300、上证 50、中证 1000 等。"
        ),
        args_schema=MarketIndicesArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="finance_search",
        description=(
            "搜索中国 A 股股票或公募基金。输入股票名/代码或基金名/代码，"
            "返回匹配的证券代码和名称列表。"
        ),
        args_schema=FinanceSearchArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="f10_data",
        description=(
            "获取个股完整 F10 基本面数据。返回公司概况、主营构成（分产品营收/毛利率）、"
            "财务摘要（营收/归母净利/EPS/同比）、盈利能力（ROE/毛利率/净利率）、"
            "区间行情与涨跌幅、主力资金流向、业绩预告、股东户数、北向资金持仓、"
            "近期公告、互动易问答。数据来源：东方财富（AKshare）。"
            "适用于深度基本面分析、辩论圆桌的事实底稿。"
        ),
        args_schema=F10DataArgs,
        authority=("retrieval",),
    ),
    # ── 双碳数据 ──────────────────────────────────────────
    ToolDef(
        name="carbon_price",
        description=(
            "从官方渠道获取碳价行情摘要：全国 CEA、CCER、地方试点等。"
            "数据源含 cets.org.cn / cneeex.com 等。禁止编造实时碳价。"
            "新闻资讯请用浏览器（invoke_context_subagent kind=execute），勿用本工具。"
        ),
        args_schema=CarbonPriceArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="carbon_policy",
        description=(
            "从官方渠道获取双碳政策法规摘要：gov.cn / ndrc.gov.cn / mee.gov.cn / miit.gov.cn 等。"
            "适用于碳达峰碳中和顶层文件、行业方案、碳市场条例等。"
            "每日新闻/政策解读请用浏览器查最新，勿用本工具冒充即时资讯。"
        ),
        args_schema=CarbonPolicyArgs,
        authority=("retrieval",),
    ),
    ToolDef(
        name="carbon_data",
        description=(
            "从官方渠道获取双碳结构化数据摘要。"
            "topic=emission 排放数据；ccer 方法学/项目；international 国际碳市场；"
            "local 地方双碳方案。新闻资讯请走浏览器工具。"
        ),
        args_schema=CarbonDataArgs,
        authority=("retrieval",),
    ),
    # ── 图表绘制（原 mermaid-diagram skill 迁移） ──────
    ToolDef(
        name="mermaid_diagram",
        description="按描述生成 Mermaid 图表（流程图/思维导图/时序图/架构图等）。",
        args_schema=MermaidDiagramArgs,
        authority=("orchestration",),
    ),
    # ── 发现 / 元工具 ─────────────────────────────────
    ToolDef(
        name="find_skills",
        description="按关键词查找可用 Skill 路由",
        args_schema=FindSkillsArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="describe_tool",
        description=(
            "查看任意工具的完整定义（描述 + 参数 schema + 使用示例）。"
            "查看后该工具会在下一轮对话变为可用，然后直接调用即可。"
            "如果你知道需要用什么工具但不清楚参数结构，先调用此工具获取详情。"
        ),
        args_schema=DescribeToolArgs,
        authority=(),
    ),
    ToolDef(
        name="search_tools",
        description="【内部】按关键词搜索原子工具；优先使用 find_skills",
        args_schema=SearchToolsArgs,
        authority=(),
    ),
    ToolDef(
        name="run_tool_batch",
        description="批量执行只读/检索工具",
        args_schema=RunToolBatchArgs,
        authority=(),
    ),
    # ── Skill 运行时 ──────────────────────────────────
    ToolDef(
        name="invoke_skill",
        description=(
            "调用已绑定 Skill：检索/文档库/技能开发等经此入口。"
            "文档库 invoke_skill(document-library, call, {operation, params})；"
            "技能开发直接调用 create_skill"
        ),
        args_schema=InvokeSkillArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="load_uploaded_skill",
        description="加载上传 Skill 的 SKILL.md",
        args_schema=LoadUploadedSkillArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="run_skill_script",
        description=(
            "执行含 main.py 的发展 Skill；entry 填 .py 路径或留空，勿填 cat 等 shell 命令。"
            "入口须 ``import skill_runtime``（否则 NameError），结论用 skill_runtime.finish"
        ),
        args_schema=RunSkillScriptArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="create_skill",
        description=(
            "创建上传型 Skill：name 为英文 slug（carbon-market-price）；"
            "数据/抓取类 extra_files 须含 main.py（import skill_runtime + skill_runtime.finish + fetch_text，"
            "禁 requests/open/subprocess）"
        ),
        args_schema=CreateUploadedSkillArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="update_uploaded_skill_file",
        description=(
            "更新 Skill 文本文件；更新 .py 文件时内容顶部必须 ``import skill_runtime``"
            "（否则执行报 NameError），结论用 skill_runtime.finish"
        ),
        args_schema=UpdateUploadedSkillFileArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="delete_uploaded_skill",
        description="删除上传型 Skill",
        args_schema=DeleteUploadedSkillArgs,
        authority=("skill_runtime",),
    ),
    ToolDef(
        name="list_agent_skills",
        description="列出平台 Skills 目录（非创建流程；生成 Skill 时勿调用）",
        args_schema=ListAgentSkillsArgs,
        authority=("skill_runtime",),
    ),
    # ── 记忆 ────────────────────────────────────────────
    ToolDef(
        name="read_agent_memory",
        description="读取用户 MEMORY.md",
        args_schema=EmptyArgs,
        authority=(),
    ),
    ToolDef(
        name="append_agent_memory",
        description="追加用户记忆",
        args_schema=AppendAgentMemoryArgs,
        authority=(),
    ),
    # ── 浏览器 ──────────────────────────────────────────
    ToolDef(
        name="browser_navigate",
        description="打开 http/https 页面",
        args_schema=BrowserNavigateArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_snapshot",
        description="获取页面可交互元素 ref",
        args_schema=EmptyArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_click",
        description="点击 ref 元素",
        args_schema=BrowserClickArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_type",
        description="向 ref 输入框填文本",
        args_schema=BrowserTypeArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_fill",
        description="批量填表",
        args_schema=BrowserFillArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_screenshot",
        description="截取当前页面",
        args_schema=BrowserScreenshotArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_save_workflow",
        description="保存浏览器录制为 RPA Skill",
        args_schema=BrowserSaveWorkflowArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_close_session",
        description="关闭浏览器会话",
        args_schema=EmptyArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_replay_workflow",
        description="回放 RPA Skill",
        args_schema=BrowserReplayWorkflowArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="browser_run_task",
        description="自然语言驱动浏览器任务",
        args_schema=BrowserRunTaskArgs,
        authority=("browser",),
    ),
    ToolDef(
        name="schedule_browser_workflow",
        description="定时回放 RPA Skill",
        args_schema=ScheduleBrowserWorkflowArgs,
        authority=("browser",),
    ),
    # ── 网页内容 ──────────────────────────────────────
    ToolDef(
        name=ATOMIC_TOOL_FETCH_URL_CONTENT,
        description=(
            "获取指定 URL 的网页正文内容（Markdown 格式）。"
            "与 web_search 不同：此工具直接读取给定 URL 的内容，不执行搜索。"
            "适合用户已提供链接、需要阅读页面全文的场景。"
            "注意：仅限可公开访问的 URL，不支持登录态页面。"
        ),
        args_schema=FetchUrlContentArgs,
        authority=("retrieval",),
    ),
    # ── 文档库 ────────────────────────────────────────
    ToolDef(
        name="search_documents_by_name",
        description="按文档标题关键词搜索并列出可见文档",
        args_schema=SearchDocumentsByNameArgs,
        authority=("document",),
    ),
    ToolDef(
        name="read_document_content",
        description=(
            "读取平台文档库指定文档的解析正文"
            "（当前版本，支持按 document_id 或 document_name）"
        ),
        args_schema=ReadDocumentContentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="list_library_documents",
        description="列出文档库文档",
        args_schema=ListLibraryDocumentsArgs,
        authority=("document",),
    ),
    ToolDef(
        name="list_manageable_documents",
        description="列出可管理文档",
        args_schema=ListManageableDocumentsArgs,
        authority=("document",),
    ),
    ToolDef(
        name="list_document_folders",
        description="列出文档库文件夹",
        args_schema=ListDocumentFoldersArgs,
        authority=("document",),
    ),
    ToolDef(
        name="create_kb_folder",
        description="新建文档库文件夹",
        args_schema=CreateKbFolderArgs,
        authority=("document",),
    ),
    ToolDef(
        name="create_library_document",
        description="写入文档库",
        args_schema=CreateLibraryDocumentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="rename_document",
        description="重命名文档",
        args_schema=RenameDocumentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="move_document",
        description="移动文档",
        args_schema=MoveDocumentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="share_document",
        description="分享文档",
        args_schema=ShareDocumentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="delete_document",
        description="删除文档（须 confirm）",
        args_schema=DeleteDocumentArgs,
        authority=("document",),
    ),
    ToolDef(
        name="update_kb_folder",
        description="更新文件夹",
        args_schema=UpdateKbFolderArgs,
        authority=("document",),
    ),
    ToolDef(
        name="delete_kb_folder",
        description="删除文件夹（须 confirm）",
        args_schema=DeleteKbFolderArgs,
        authority=("document",),
    ),
    ToolDef(
        name="sync_document_knowledge",
        description="同步文档到知识库",
        args_schema=SyncDocumentKnowledgeArgs,
        authority=("document",),
    ),
    ToolDef(
        name="reindex_document",
        description="重建文档索引",
        args_schema=ReindexDocumentArgs,
        authority=("document",),
    ),
    # ── 平台 ──────────────────────────────────────────
    ToolDef(
        name="list_todos",
        description="列出待办",
        args_schema=ListTodosArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="create_todo",
        description="创建待办",
        args_schema=CreateTodoArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="update_todo",
        description="更新待办",
        args_schema=UpdateTodoArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="delete_todo",
        description="删除待办",
        args_schema=DeleteTodoArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="send_notification",
        description=(
            "立即发送一条系统站内通知给当前用户。"
            "当用户要求「通知我」「提醒我」「发消息给我」时使用。"
            "返回通知 ID 和发送结果。"
            "⚠ 不可用于发送外部邮件、短信、第三方应用消息。"
            "⚠ 通知由用户在通知中心查阅，不强制弹窗。"
            "如需在指定未来时间发送，请改用 schedule_notification。"
        ),
        args_schema=SendNotificationArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="schedule_notification",
        description=(
            "安排一条定时站内通知，在指定时间送达用户。"
            "当用户说「X秒/分钟后提醒我」「定时通知我」「设置提醒」时使用。"
            "scheduled_at 参数推荐用相对时间表达式："
            "'8s' / '8秒' / '8秒后' → 8 秒后；"
            "'5分钟' / '5m' → 5 分钟后；"
            "'2小时' / '2h' → 2 小时后。"
            "也支持 ISO 8601 绝对时间（含时区），如 ``2026-07-09T16:30:00+08:00``。"
            "返回定时通知 ID 和计划发送时间。"
            "⚠ 不支持周期重复（如'每天提醒'需多次调用）。"
            "⚠ 如需立即发送请用 send_notification，不要用 schedule_nofication 传当前时间。"
        ),
        args_schema=ScheduleNotificationArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="list_scheduled_notifications",
        description=(
            "查看当前用户所有待发送的定时通知列表（未发送、未取消的）。"
            "当用户问「有哪些定时通知」「查看我的提醒」「列出定时任务」时使用。"
            "返回通知标题、计划发送时间等列表。"
            "已发送或已取消的通知不会出现在结果中。"
        ),
        args_schema=ListScheduledNotificationsArgs,
        authority=("platform",),
    ),
    ToolDef(
        name="cancel_scheduled_notification",
        description=(
            "取消一条尚未发送的定时通知。"
            "当用户说「取消提醒」「取消定时通知」时使用。"
            "需要传 notification_id"
            "（来自 list_scheduled_notifications 或 schedule_notification 的返回）。"
            "⚠ 已发送的通知无法取消。"
        ),
        args_schema=CancelScheduledNotificationArgs,
        authority=("platform",),
    ),
    # ── 用户交互 ────────────────────────────────────
    ToolDef(
        name="ask_user_choice",
        description=(
            "向用户提出方案选择，让用户从多个选项中挑选一个再继续执行。"
            "当已有信息不足以做单一决策、存在多种合理方案、或用户偏好会影响结果时，"
            "必须使用此工具询问用户，不要替用户做不确定的猜测。"
            "适用场景举例：导出格式（PDF/Word/Markdown）、分析时间范围、"
            "报告风格偏好、多种数据可视化方案、多个执行路径等。"
            "question 参数清晰描述需要用户决定什么，"
            "options 参数列出 2-6 个简洁明了的选项供用户选择。"
        ),
        args_schema=AskUserChoiceArgs,
        authority=(),
    ),
    # ── 智能体协作 ──────────────────────────────────
    ToolDef(
        name="invoke_context_subagent",
        description=(
            "委托子 Agent 执行任务。这是三种子智能体的统一入口：\n"
            "- kind=search：深度联网检索（搜索+知识库+本体+图谱，多源交叉验证，直接回答）\n"
            "- kind=use：执行已有 Skill（按需调用技能的每一步）\n"
            "- kind=execute：严格按父智能体编排的步骤执行（浏览器自动化、定时器、通知发送等具体操作）\n"
            "所有需要联网查信息/调研/研究的需求统一使用 kind=search。"
        ),
        args_schema=InvokeContextSubagentArgs,
        authority=("orchestration",),
    ),
    ToolDef(
        name="request_orchestrator_assist",
        description=(
            "本域无法完成时向调度智能体反馈，"
            "由调度层协调其他专精协助后再交还你续办"
        ),
        args_schema=RequestOrchestratorAssistArgs,
        authority=("orchestration",),
    ),
    # ── 用户管理 ────────────────────────────────────
    ToolDef(
        name="list_users",
        description="列出用户",
        args_schema=ListUsersArgs,
        authority=("admin_user",),
    ),
    ToolDef(
        name="create_user",
        description="创建用户",
        args_schema=CreateUserArgs,
        authority=("admin_user",),
    ),
    ToolDef(
        name="update_user",
        description="更新用户",
        args_schema=UpdateUserArgs,
        authority=("admin_user",),
    ),
    ToolDef(
        name="delete_user",
        description="删除用户（须 confirm）",
        args_schema=DeleteUserArgs,
        authority=("admin_user",),
    ),
    # ── 部门管理 ────────────────────────────────────
    ToolDef(
        name="list_departments",
        description="列出部门",
        args_schema=EmptyArgs,
        authority=("admin_dept",),
    ),
    ToolDef(
        name="create_department",
        description="创建部门",
        args_schema=CreateDepartmentArgs,
        authority=("admin_dept",),
    ),
    ToolDef(
        name="update_department",
        description="更新部门",
        args_schema=UpdateDepartmentArgs,
        authority=("admin_dept",),
    ),
    ToolDef(
        name="delete_department",
        description="删除部门（须 confirm）",
        args_schema=DeleteDepartmentArgs,
        authority=("admin_dept",),
    ),
]

# ── 向后兼容别名（TOOL_DEFINITIONS 保持 (描述, model) 元组格式） ──
TOOL_DEFINITIONS: dict[str, tuple[str, type[BaseModel]]] = {
    t.name: (t.description, t.args_schema) for t in ALL_TOOLS
}

# ── 运行时参数校验 ──────────────────────────────────────
_TOOL_BY_NAME: dict[str, ToolDef] = {t.name: t for t in ALL_TOOLS}

TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    t.name: t.args_schema for t in ALL_TOOLS
}


def get_tool_def(name: str) -> ToolDef | None:
    """LangGraph 风格的 BaseTool 查找：按名称取工具定义。

    返回 ``ToolDef``（含 name / description / args_schema / authority），
    ``None`` 表示未注册。
    """
    return _TOOL_BY_NAME.get(name)


# ── 按 authority 自动分组的工具名常量（保持向后兼容） ──
RETRIEVAL_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "retrieval" in t.authority
)

BROWSER_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "browser" in t.authority
)

DOCUMENT_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "document" in t.authority
)

ORCHESTRATION_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "orchestration" in t.authority
)

PLATFORM_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "platform" in t.authority
)

SKILL_RUNTIME_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "skill_runtime" in t.authority
)

# 记忆由系统自动处理；原子读写仅在内部 Tool 池
AGENT_SKILL_TOOL_NAMES: tuple[str, ...] = SKILL_RUNTIME_TOOL_NAMES

ADMIN_USER_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "admin_user" in t.authority
)

ADMIN_DEPT_TOOL_NAMES: tuple[str, ...] = tuple(
    t.name for t in ALL_TOOLS if "admin_dept" in t.authority
)


def build_tool_specs(names: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    """批量构建 OpenAI function calling spec。

    描述优先从 tools/definitions/<name>.md 加载（热生效），
    无 MD 文件时回退 TOOL_DEFINITIONS 的硬编码描述。
    """
    specs: list[dict[str, Any]] = []
    for name in names:
        hardcoded_desc, model = TOOL_DEFINITIONS[name]
        md_desc = get_tool_description(name)
        desc = md_desc if md_desc else hardcoded_desc
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
