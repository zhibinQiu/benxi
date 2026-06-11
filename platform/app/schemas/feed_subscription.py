from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FeedSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    feed_url: str = Field(min_length=8, max_length=1024)
    kind: Literal["rss", "website"] = "rss"
    category: str = Field(default="", max_length=64)


class FeedPresetOut(BaseModel):
    name: str
    feed_url: str
    site_url: str = ""
    kind: str = "rss"
    category: str = ""


class FeedSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    feed_url: str
    site_url: str
    kind: str
    category: str
    sync_status: str
    sync_message: str
    last_sync_at: datetime | None
    entry_count: int = 0
    subscribed_at: datetime | None = None


class FeedEntryOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_kind: str
    category: str
    title: str
    summary: str
    link: str
    publish_at: datetime | None
    fetched_at: datetime
    imported: bool = False
    document_id: uuid.UUID | None = None


class FeedEntryDetailOut(FeedEntryOut):
    content_html: str


class FeedImportIn(BaseModel):
    """导入文档库；分级固定为「个人级」(personal)，dept_id 无效。"""
    scope: str = "personal"
    dept_id: uuid.UUID | None = None
    sync_knowflow: bool = True


class FeedImportOut(BaseModel):
    document_id: uuid.UUID
    knowflow_synced: bool = False


class FeedSyncOut(BaseModel):
    synced_entries: int
    message: str
