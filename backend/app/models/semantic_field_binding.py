"""问数映射：概念属性 → 事务库表列（自动发现结果落库，非 TBox）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SemanticFieldBinding(Base):
    """概念.属性 → SQL 表列 / 联查模板。"""

    __tablename__ = "semantic_field_bindings"
    __table_args__ = (
        UniqueConstraint(
            "concept", "property_key", "source", name="uq_semantic_field_binding"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    concept: Mapped[str] = mapped_column(String(64), index=True)
    property_key: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(16), default="sql")  # sql | document
    table_name: Mapped[str] = mapped_column(String(128), default="")
    column_name: Mapped[str] = mapped_column(String(128), default="")
    join_template: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # auto | manual | seed
    origin: Mapped[str] = mapped_column(String(16), default="auto")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | pending
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
