"""Agent Skills 核心类型 — agentkit 泛型 + 平台 ORM 上下文。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentkit_skills.types import SkillDefinition as AgentSkillDefinition
from agentkit_skills.types import SkillKind, SkillReadiness, SkillSource, SkillToolSpec
from sqlalchemy.orm import Session

from app.models.org import User

SkillHandler = Callable[["SkillInvocationContext", dict[str, Any]], Awaitable["SkillInvocationResult"]]


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """统一的 Skill 描述（内置或上传），skill_id 使用 uuid.UUID。

    .. hint::
        ``agentkit_skills.SkillDefinition`` 是同一 dataclass 的泛化版本（skill_id: str）。
        本类型用于含 DB 回话的平台上下文；纯代理场景可直接用 agentkit 版本。
    """

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
    catalog_tier: str = "resident"
    created_at: datetime | None = None
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""


@dataclass(slots=True)
class SkillInvocationContext:
    db: Session
    user: User
    conversation_id: str | None = None
    attachment_session_id: str | None = None
    doc_ids: list[uuid.UUID] | None = None
    skill_name: str | None = None
    belong_agent: str | None = None
    trace_id: str | None = None
    user_message: str = ""
    loop_state: dict[str, Any] | None = None


@dataclass(slots=True)
class SkillInvocationResult:
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None


def to_agentkit_skill(defn: SkillDefinition) -> AgentSkillDefinition:
    """将平台 SkillDefinition 转为 agentkit 泛化版本（skill_id 转 str）。"""
    return AgentSkillDefinition(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        source=defn.source,
        tools=defn.tools,
        orchestrated_tools=defn.orchestrated_tools,
        feature_id=defn.feature_id,
        permission_code=defn.permission_code,
        readiness=defn.readiness,
        skill_id=str(defn.skill_id) if defn.skill_id else None,
        route=defn.route,
        source_type=defn.source_type,
        catalog_visible=defn.catalog_visible,
        catalog_tier=defn.catalog_tier,
        use_when=defn.use_when,
        dont_use_when=defn.dont_use_when,
        output=defn.output,
    )


def from_agentkit_skill(defn: AgentSkillDefinition) -> SkillDefinition:
    """将 agentkit SkillDefinition 转为平台版本（skill_id 转 uuid.UUID）。"""
    return SkillDefinition(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        source=defn.source,
        tools=defn.tools,
        orchestrated_tools=defn.orchestrated_tools,
        feature_id=defn.feature_id,
        permission_code=defn.permission_code,
        readiness=defn.readiness,
        skill_id=uuid.UUID(defn.skill_id) if defn.skill_id else None,
        route=defn.route,
        source_type=defn.source_type,
        catalog_visible=defn.catalog_visible,
        catalog_tier=defn.catalog_tier,
        use_when=defn.use_when,
        dont_use_when=defn.dont_use_when,
        output=defn.output,
    )


__all__ = [
    "AgentSkillDefinition",
    "SkillDefinition",
    "SkillHandler",
    "SkillInvocationContext",
    "SkillInvocationResult",
    "SkillKind",
    "SkillReadiness",
    "SkillSource",
    "SkillToolSpec",
    "from_agentkit_skill",
    "to_agentkit_skill",
]
