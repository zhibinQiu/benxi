"""平台用户与 RAGFlow / KnowFlow 账号映射（阶段 2 SSO 使用）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RagflowAccountLink(Base):
    __tablename__ = "ragflow_account_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True
    )
    ragflow_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ragflow_email: Mapped[str] = mapped_column(String(255), index=True)
    ragflow_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    ragflow_password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
