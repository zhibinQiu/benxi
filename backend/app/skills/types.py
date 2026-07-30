"""平台 Skill 类型 — 在 ``app.agent.skills`` 泛型之上叠加 ORM / 用户上下文。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.agent_loop_state import LoopState

from app.agent.skills.types import SkillKind, SkillReadiness, SkillSource, SkillToolSpec
from sqlalchemy.orm import Session

from app.models.org import User

SkillHandler = Callable[["SkillInvocationContext", dict[str, Any]], Awaitable["SkillInvocationResult"]]


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """平台 Skill 描述（内置或上传）；``skill_id`` 为 UUID。

    纯运行时场景可直接使用 ``app.agent.skills.types.SkillDefinition``（``skill_id: str``）。
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
    """单次 Skill 调用上下文（DB 会话、用户、附件与进度回调）。"""

    db: Session
    user: User
    conversation_id: str | None = None
    attachment_session_id: str | None = None
    doc_ids: list[uuid.UUID] | None = None
    skill_name: str | None = None
    belong_agent: str | None = None
    trace_id: str | None = None
    user_message: str = ""
    loop_state: LoopState | None = None
    progress_callback: Callable[[int, str], None] | None = None


@dataclass(slots=True)
class SkillInvocationResult:
    """Skill 调用结果。"""

    ok: bool
    summary: str
    data: Any = None
    error: str | None = None


__all__ = [
    "SkillDefinition",
    "SkillHandler",
    "SkillInvocationContext",
    "SkillInvocationResult",
    "SkillKind",
    "SkillReadiness",
    "SkillSource",
    "SkillToolSpec",
]
