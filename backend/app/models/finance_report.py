import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinanceReport(Base):
    """理财报告任务。"""

    __tablename__ = "finance_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    stock_code: Mapped[str] = mapped_column(String(32), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 报告类型: ai / roundtable / vpa
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # 圆桌相关参数
    roundtable_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    research_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # AI 解读补充上下文
    ai_context: Mapped[str] = mapped_column(Text, default="")

    # 任务状态: pending / running / completed / failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    # 报告内容（完成时填充）
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 进度百分比
    progress: Mapped[int] = mapped_column(Integer, default=0)

    # 在线阅读次数
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    # 公开分享令牌（无需登录即可查看）
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    # 关联系统 Job ID（用于在后台任务窗口展示进度）
    system_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
