"""碳市场历史行情（CEA/CCER 日行情，持久化于数据库）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CeaDailyQuote(Base):
    __tablename__ = "cea_daily_quotes"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_cny: Mapped[float] = mapped_column(Float, nullable=False)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_tco2: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CcerDailyQuote(Base):
    __tablename__ = "ccer_daily_quotes"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    traded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    close_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_tco2: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    amount_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
