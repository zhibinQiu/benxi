"""提示词管理 — Pydantic schemas。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PromptCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1)
    category: str = Field("", max_length=64)


class PromptUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    content: str | None = Field(None, min_length=1)
    category: str | None = Field(None, max_length=64)


class PromptOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    content: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptCategoryCount(BaseModel):
    category: str
    count: int
