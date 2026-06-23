"""统一资讯订阅 API 模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionIngestIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class SubscriptionItemOut(BaseModel):
    ref: str
    id: uuid.UUID
    title: str
    summary: str = ""
    link: str = ""
    cover_url: str = ""
    is_wechat: bool = False
    publish_at: datetime | None = None
    created_at: datetime | None = None
    imported: bool = False
    document_id: uuid.UUID | None = None


class SubscriptionItemDetailOut(SubscriptionItemOut):
    content_html: str = ""
    content_markdown: str = ""
    author: str = ""


class SubscriptionImportIn(BaseModel):
    sync_knowflow: bool = True


class SubscriptionImportOut(BaseModel):
    document_id: uuid.UUID
    knowflow_synced: bool = False
    queued: bool = False
    job_id: uuid.UUID | None = None
