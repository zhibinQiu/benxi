from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SpeechSegmentOut(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class SpeechSegmentIn(BaseModel):
    speaker: str
    start: float = 0.0
    end: float = 0.0
    text: str = ""


class SpeechSummaryBlockOut(BaseModel):
    speaker: str
    start: float
    end: float
    time_range: str
    summary: str


class SpeechMetaOut(BaseModel):
    configured: bool
    provider: str
    model: str
    max_file_mb: int
    accepted_extensions: list[str]
    default_language: str | None = None
    diarization_available: bool = False
    summarize_available: bool = False
    summarize_model: str | None = None
    service_hint: str | None = None


class SpeechTranscribeOut(BaseModel):
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    model: str
    source_filename: str | None = None
    segments: list[SpeechSegmentOut] = Field(default_factory=list)


class SpeechSummarizeIn(BaseModel):
    text: str = Field("", description="Flat transcript; used when segments empty")
    style: str = Field("minutes", description="minutes | brief | detailed")
    segments: list[SpeechSegmentIn] = Field(default_factory=list)


class SpeechSummarizeOut(BaseModel):
    summary: str
    model: str
    blocks: list[SpeechSummaryBlockOut] = Field(default_factory=list)


class MeetingRecordSaveIn(BaseModel):
    id: uuid.UUID | None = None
    title: str = Field("", max_length=256)
    segments: list[SpeechSegmentIn] = Field(default_factory=list)
    summary: str | None = None
    summary_blocks: list[SpeechSummaryBlockOut] | None = None
    meta: dict | None = None


class MeetingRecordListItem(BaseModel):
    id: uuid.UUID
    title: str
    segment_count: int
    has_summary: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingRecordOut(BaseModel):
    id: uuid.UUID
    title: str
    segments: list[SpeechSegmentOut]
    summary: str | None = None
    summary_blocks: list[SpeechSummaryBlockOut] = Field(default_factory=list)
    meta: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
