from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SkillSourceOut(StrEnum):
    BUILTIN = "builtin"
    UPLOADED = "uploaded"
    MCP = "mcp"


class SkillReadinessOut(StrEnum):
    READY = "ready"
    STUB = "stub"
    DISABLED = "disabled"
    NO_PERMISSION = "no_permission"


class SkillToolOut(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)


class SkillKindOut(StrEnum):
    BUILTIN = "builtin"
    DEVELOPED = "developed"


class AgentToolCategoryOut(StrEnum):
    WEB = "web"
    KNOWLEDGE = "knowledge"
    GRAPH = "graph"
    SKILL_MGMT = "skill_mgmt"
    MEMORY = "memory"
    DOCUMENT = "document"
    PLATFORM = "platform"
    ADMIN = "admin"
    BROWSER = "browser"


class RateLimitOut(BaseModel):
    qps: int = 20


class AgentToolOut(BaseModel):
    """全局 ToolCenter 注册项（管理页只读）。"""

    name: str
    tool_id: str = ""
    tool_type: str = ""
    description: str
    category: AgentToolCategoryOut
    available: bool = True
    availability_note: str = ""
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    rate_limit: RateLimitOut = Field(default_factory=RateLimitOut)
    tool_version: str = "v1.0"


class AgentSkillSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    enabled: bool
    scope: str
    file_count: int
    total_bytes: int
    source_type: str
    created_at: datetime
    updated_at: datetime


class AgentSkillDetailOut(AgentSkillSummaryOut):
    frontmatter: dict | None = None
    files: list[str] = Field(default_factory=list)


class AgentSkillCatalogItemOut(BaseModel):
    """供智能体发现阶段注入的轻量目录项。"""

    name: str
    description: str
    source: SkillSourceOut = SkillSourceOut.UPLOADED
    kind: SkillKindOut = SkillKindOut.DEVELOPED
    title: str = ""
    readiness: SkillReadinessOut = SkillReadinessOut.READY
    orchestrated_tools: list[str] = Field(default_factory=list)


class UnifiedSkillOut(BaseModel):
    name: str
    title: str
    description: str
    source: SkillSourceOut
    kind: SkillKindOut
    enabled: bool
    readiness: SkillReadinessOut
    feature_id: str | None = None
    permission_code: str | None = None
    route: str | None = None
    orchestrated_tools: list[str] = Field(default_factory=list)
    skill_id: uuid.UUID | None = None
    source_type: str | None = None
    created_at: datetime | None = None


class BuiltinSkillPatchIn(BaseModel):
    enabled: bool


class SkillInvokeIn(BaseModel):
    skill_name: str
    tool_name: str = "search"
    params: dict = Field(default_factory=dict)


class SkillInvokeOut(BaseModel):
    ok: bool
    summary: str
    data: dict | list | str | None = None
    error: str | None = None


class AgentSkillUploadOut(BaseModel):
    skills: list[AgentSkillSummaryOut]
    total: int


class AgentSkillUpdateIn(BaseModel):
    enabled: bool | None = None
    description: str | None = None


class AgentSkillCreateIn(BaseModel):
    name: str
    description: str
    skill_md_body: str = Field(description="SKILL.md 正文（不含 frontmatter）")
    replace_existing: bool = False


class AgentSkillFileUpdateIn(BaseModel):
    content: str


class AgentMemoryOut(BaseModel):
    content: str


class AgentMemoryUpdateIn(BaseModel):
    content: str


class AgentSkillFileOut(BaseModel):
    path: str
    size: int
    content_type: str


class AgentSkillFileContentOut(BaseModel):
    path: str
    content_type: str
    text: str | None = None
    base64: str | None = None
    readonly: bool = False


class RoutingCatalogOut(BaseModel):
    """调度路由目录（skills.md / agents.md）— 只读，随后台自动更新。"""

    path: str
    text: str
    content_type: str = "text/markdown"
    readonly: bool = True
