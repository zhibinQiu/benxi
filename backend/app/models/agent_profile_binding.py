"""智能体配置 — 启停与 Skill 白名单（系统智能体不可新建）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentProfileBinding(Base):
    __tablename__ = "agent_profile_bindings"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    service_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    skill_names: Mapped[list] = mapped_column(JSONB, default=list)
    runtime_tool_names: Mapped[list] = mapped_column(JSONB, default=list)
    config_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
