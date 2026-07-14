"""ToolCenter 执行期上下文 — 与 ToolCallRequest 分离。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.agent_loop_state import LoopState

from sqlalchemy.orm import Session

from app.models.org import User


@dataclass(slots=True)
class ToolRuntimeContext:
    """执行期上下文 — 仅 executor 持有，不写入 ToolCallRequest。"""

    db: Session
    user: User
    conversation_id: str | None = None
    attachment_session_id: str | None = None
    user_message: str = ""
    loop_state: LoopState | None = field(default=None)
