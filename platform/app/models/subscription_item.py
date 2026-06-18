"""网站收藏：用户已移除条目（按链接去重，避免同步或重复源再次展示）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubscriptionItemRemoval(Base):
    __tablename__ = "subscription_item_removals"
    __table_args__ = (
        UniqueConstraint("user_id", "link_key", name="uq_subscription_item_removal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    link_key: Mapped[str] = mapped_column(String(64), index=True)
    link: Mapped[str] = mapped_column(String(1024), default="")
    removed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
