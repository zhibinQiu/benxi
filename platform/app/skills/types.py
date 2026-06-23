"""Agent Skills 核心类型 — 内置能力与上传包统一抽象。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.models.org import User


class SkillSource(StrEnum):
    BUILTIN = "builtin"
    UPLOADED = "uploaded"


class SkillKind(StrEnum):
    """技能分层：内置技能 vs 发展技能（上传 / Agent 生成）。"""

    BUILTIN = "builtin"
    DEVELOPED = "developed"


class SkillReadiness(StrEnum):
    """Skill 对智能体调用的就绪程度。"""

    READY = "ready"  # 工具已实现，可被 agent 调用
    STUB = "stub"  # 已注册，handler 返回占位/引导信息
    DISABLED = "disabled"  # 管理员或功能开关关闭
    NO_PERMISSION = "no_permission"  # 当前用户无权限


SkillHandler = Callable[["SkillInvocationContext", dict[str, Any]], Awaitable["SkillInvocationResult"]]


@dataclass(frozen=True, slots=True)
class SkillToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: SkillHandler | None = None


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """统一的 Skill 描述（内置或上传）。"""

    name: str
    title: str
    description: str
    source: SkillSource
    tools: tuple[SkillToolSpec, ...] = ()
    orchestrated_tools: tuple[str, ...] = ()
    feature_id: str | None = None
    permission_code: str | None = None
    readiness: SkillReadiness = SkillReadiness.STUB
    skill_id: uuid.UUID | None = None
    route: str | None = None
    source_type: str | None = None
    catalog_visible: bool = True
    """是否出现在技能目录与管理页；单原子工具映射为 False，仅保留内部 handler。"""


@dataclass(slots=True)
class SkillInvocationContext:
    db: Session
    user: User
    conversation_id: str | None = None
    attachment_session_id: str | None = None
    doc_ids: list[uuid.UUID] | None = None


@dataclass(slots=True)
class SkillInvocationResult:
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None
