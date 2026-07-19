"""工作笔记 — Pydantic schemas。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NoteFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    parent_id: str | None = None


class NoteFolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    parent_id: str | None = None


class NoteFolderOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    note_count: int = 0

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    folder_id: str | None = None
    title: str = ""
    content: str = ""


class NoteUpdate(BaseModel):
    folder_id: str | None = None
    title: str | None = None
    content: str | None = None
    is_pinned: bool | None = None


class NoteOut(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    content: str
    is_pinned: bool
    sort_order: int
    share_token: str | None = None
    view_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteSummaryOut(BaseModel):
    """笔记列表摘要（不含 content 正文，减少传输量）。"""
    id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    is_pinned: bool
    sort_order: int
    share_token: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteShareOut(BaseModel):
    share_token: str


class NoteShareIn(BaseModel):
    """生成分享链接；regenerate=True 时覆盖旧令牌。"""
    regenerate: bool = True


class NotePublishIn(BaseModel):
    """发布选项：可多选。"""
    to_library: bool = False
    share_link: bool = False


class NotePublishOut(BaseModel):
    share_token: str | None = None
    library_queued: bool = False
    message: str = ""


class NoteBatchDelete(BaseModel):
    ids: list[str]


class ImageUploadOut(BaseModel):
    url: str


class NotePolishIn(BaseModel):
    content: str = Field(..., max_length=50000)
    direction: str = Field("", max_length=500, description="润色方向/风格要求")


class NotePolishOut(BaseModel):
    content: str
