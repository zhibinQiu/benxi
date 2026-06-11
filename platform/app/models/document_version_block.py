"""文档版本结构化分块（OCR / 版面解析，含页码与 bbox）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentVersionBlock(Base):
    __tablename__ = "document_version_blocks"
    __table_args__ = (
        UniqueConstraint("version_id", "block_index", name="uq_doc_version_block_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    block_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=1)
    block_type: Mapped[str] = mapped_column(String(32), default="text")
    text: Mapped[str] = mapped_column(Text, default="")
    bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
