"""本析智能平台级设置（单例）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SINGLETON_ID = 1


class PlatformAiHomeSettings(Base):
    __tablename__ = "platform_ai_home_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    openai_api_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
