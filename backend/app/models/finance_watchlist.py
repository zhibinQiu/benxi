import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinanceWatchlistItem(Base):
    __tablename__ = "finance_watchlist_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_watchlist_user_type_code", "user_id", "asset_type", "asset_code", unique=True),
    )
