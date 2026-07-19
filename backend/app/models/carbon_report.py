"""双碳助手报告任务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CarbonReport(Base):
    """双碳报告 / 减碳策略任务。"""

    __tablename__ = "carbon_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )

    # 主题：如「全国碳市场」「钢铁行业」
    subject: Mapped[str] = mapped_column(String(128), nullable=False)

    # market_brief | policy_digest | strategy
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 策略类可选参数
    industry: Mapped[str] = mapped_column(String(64), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    target_year: Mapped[str] = mapped_column(String(16), default="")

    ai_context: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    system_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
