"""Agent Skills 核心类型 — 内置能力与扩展包统一抽象。

``SkillInvocationContext`` 使用 ``extras`` 字典承载宿主字段（db、user 等），
避免本库依赖 SQLAlchemy / FastAPI。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SkillSource(StrEnum):
    BUILTIN = "builtin"
    UPLOADED = "uploaded"
    MCP = "mcp"


class SkillKind(StrEnum):
    """技能分层：内置技能 vs 发展技能（上传 / Agent 生成）。"""

    BUILTIN = "builtin"
    DEVELOPED = "developed"


class SkillCategory(StrEnum):
    """技能类型：编排工作流 / 指令模板 / 工具集。

    workflow:   多步编排工作流，组合多个原子工具按特定流程执行。
    instruction: LLM 指令模板或提示词，引导智能体按特定方式输出。
    toolset:     原子工具轻量封装，本质上就是一组 CRUD/工具操作的直接调用。
    """

    WORKFLOW = "workflow"
    INSTRUCTION = "instruction"
    TOOLSET = "toolset"


class SkillReadiness(StrEnum):
    """Skill 对智能体调用的就绪程度。"""

    READY = "ready"
    STUB = "stub"
    DISABLED = "disabled"
    NO_PERMISSION = "no_permission"


SkillHandler = Callable[["SkillInvocationContext", dict[str, Any]], Awaitable["SkillInvocationResult"]]


@dataclass(frozen=True, slots=True)
class SkillToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: SkillHandler | None = None


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """统一的 Skill 描述（内置、上传或 MCP 代理）。"""

    name: str
    title: str
    description: str
    source: SkillSource
    tools: tuple[SkillToolSpec, ...] = ()
    orchestrated_tools: tuple[str, ...] = ()
    feature_id: str | None = None
    permission_code: str | None = None
    readiness: SkillReadiness = SkillReadiness.STUB
    skill_id: str | None = None
    route: str | None = None
    source_type: str | None = None
    catalog_visible: bool = True
    catalog_tier: str = "resident"
    skill_category: SkillCategory = SkillCategory.WORKFLOW
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""


@dataclass(slots=True)
class SkillInvocationContext:
    """Skill 调用上下文；``extras`` 由宿主注入任意业务字段。"""

    conversation_id: str | None = None
    trace_id: str | None = None
    skill_name: str | None = None
    belong_agent: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillInvocationResult:
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None
