"""分级知识库注册表：公司/部门/个人各一份 KnowFlow dataset，不按用户复制。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SCOPE_COMPANY = "company"
SCOPE_DEPARTMENT = "department"
SCOPE_PERSONAL = "personal"


class RagflowScopeDataset(Base):
    __tablename__ = "ragflow_scope_datasets"
    __table_args__ = (
        UniqueConstraint("scope", "scope_key", name="uq_ragflow_scope_datasets_scope_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope: Mapped[str] = mapped_column(String(16), index=True)
    scope_key: Mapped[str] = mapped_column(String(64), index=True)
    ragflow_dataset_id: Mapped[str] = mapped_column(String(64))
    owner_ragflow_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
