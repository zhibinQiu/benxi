"""数字机器人 RPA 任务 — 支持定时/周期/立即执行。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DigitalRobotTask(Base):
    __tablename__ = "digital_robot_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")

    # RPA 执行计划（JSON）
    plan_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 调度方式
    #  - "immediate": 立即执行
    #  - "scheduled": 指定时间执行
    #  - "periodic": 周期执行（cron 或 interval）
    schedule_mode: Mapped[str] = mapped_column(
        String(32), default="immediate", index=True
    )
    # 一次性定时
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # 周期：cron 表达式（如 "0 9 * * 1-5"）
    cron_expression: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    # 周期：间隔秒数（如 3600 = 每小时）
    interval_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # 状态
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )
    # 上次/本次执行结果
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_screenshot_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
