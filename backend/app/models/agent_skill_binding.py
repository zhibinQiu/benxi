"""内置 Skill 管理员启停覆盖 + 标题/描述覆盖。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentSkillBinding(Base):
    __tablename__ = "agent_skill_bindings"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    title_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    description_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
