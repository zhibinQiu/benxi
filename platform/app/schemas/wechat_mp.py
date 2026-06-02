from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WechatMpParseUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class WechatMpParseUrlOut(BaseModel):
    title: str
    summary: str
    cover_url: str
    author: str
    biz: str
    account_name: str
    original_url: str
    publish_at: datetime | None = None


class WechatMpSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    sample_url: str | None = Field(default=None, max_length=2048)
    biz: str | None = Field(
        default=None,
        max_length=128,
        description="可选，链接解析失败时手动填写 __biz= 后的字符串",
    )


class WechatMpSourceOut(BaseModel):
    id: uuid.UUID
    biz: str
    name: str
    avatar_url: str
    intro: str
    sync_status: str
    sync_message: str
    last_sync_at: datetime | None
    article_count: int = 0
    subscribed_at: datetime | None = None

    model_config = {"from_attributes": True}


class WechatMpArticleOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    title: str
    summary: str
    cover_url: str
    author: str
    publish_at: datetime | None
    original_url: str
    fetched_at: datetime
    imported: bool = False
    document_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class WechatMpArticleDetailOut(WechatMpArticleOut):
    content_html: str


class WechatMpImportIn(BaseModel):
    """导入文档库；分级固定为「我的」(personal)，dept_id 无效。"""
    scope: str = "personal"
    dept_id: uuid.UUID | None = None
    sync_knowflow: bool = True


class WechatMpImportOut(BaseModel):
    document_id: uuid.UUID
    knowflow_synced: bool = False


class WechatMpSyncOut(BaseModel):
    synced_articles: int
    message: str
