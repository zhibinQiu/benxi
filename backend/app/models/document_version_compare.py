"""单文档多版本预对比：关系表 + 差异项持久化。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VersionCompareRelationType(str, enum.Enum):
    baseline_v0 = "baseline_v0"
    adjacent = "adjacent"
    on_demand = "on_demand"


class VersionCompareStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class DocumentVersionCompareRelation(Base):
    """版本对对比关系（预计算或按需）。"""

    __tablename__ = "document_version_compare_relations"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "from_version_id",
            "to_version_id",
            name="uq_doc_version_compare_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    from_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    to_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), default="on_demand", index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=VersionCompareStatus.pending.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    diff_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_summary_status: Mapped[str] = mapped_column(String(16), default="pending")

    diff_items: Mapped[list["DocumentVersionDiffItem"]] = relationship(
        back_populates="relation", cascade="all, delete-orphan"
    )


class DocumentVersionDiffItem(Base):
    """版本对预计算/按需 diff 条目。"""

    __tablename__ = "document_version_diff_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    relation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_version_compare_relations.id", ondelete="CASCADE"),
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    from_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    to_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    diff_type: Mapped[str] = mapped_column(String(16))
    text_left: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_right: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    relation: Mapped[DocumentVersionCompareRelation] = relationship(
        back_populates="diff_items"
    )
