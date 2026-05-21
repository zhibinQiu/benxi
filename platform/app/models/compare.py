"""Document compare jobs (independent from generic Job table)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CompareStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class CompareJob(Base):
    __tablename__ = "compare_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    base_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_ids: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(16), default=CompareStatus.pending.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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

    diff_items: Mapped[list["CompareDiffItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    search_hits: Mapped[list["CompareSearchHit"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class CompareDiffItem(Base):
    __tablename__ = "compare_diff_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compare_jobs.id", ondelete="CASCADE"), index=True
    )
    pair_key: Mapped[str] = mapped_column(String(64))
    doc_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    doc_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    diff_type: Mapped[str] = mapped_column(String(16))
    text_left: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_right: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job: Mapped[CompareJob] = relationship(back_populates="diff_items")


class CompareSearchHit(Base):
    __tablename__ = "compare_search_hits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compare_jobs.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(String(512))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    snippet: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    anchor_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job: Mapped[CompareJob] = relationship(back_populates="search_hits")
