"""理财助手 — Pydantic schemas。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WatchlistItemCreate(BaseModel):
    asset_type: str = Field(..., pattern="^(stock|fund|crypto)$")
    asset_code: str = Field(..., min_length=1, max_length=64)
    asset_name: str = Field(..., min_length=1, max_length=128)


class WatchlistItemOut(BaseModel):
    id: uuid.UUID
    asset_type: str
    asset_code: str
    asset_name: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportSubmit(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=32)
    stock_name: str = Field(..., min_length=1, max_length=128)
    report_type: str = Field(..., pattern="^(ai|roundtable|vpa)$")
    roundtable_type: str | None = Field(None, pattern="^(debate|research)?$")
    research_direction: str | None = Field(None, pattern="^(fundamental|shortterm)?$")
    ai_context: str = Field("", max_length=1000)


class ReportOut(BaseModel):
    id: uuid.UUID
    stock_code: str
    stock_name: str
    report_type: str
    roundtable_type: str | None
    research_direction: str | None
    ai_context: str
    status: str
    content: str | None
    error_message: str | None
    progress: int
    view_count: int = 0
    share_token: str | None = None
    system_job_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ReportImportLibraryOut(BaseModel):
    document_id: uuid.UUID
    title: str
    knowflow_synced: bool = False
    message: str = ""
