from __future__ import annotations

from pydantic import BaseModel, Field


class SegmentOut(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class MetaOut(BaseModel):
    engine: str = "funasr"
    asr_model: str
    vad_model: str
    punc_model: str
    spk_model: str | None = None
    diarization_available: bool
    max_file_mb: int
    models_dir: str


class TranscribeOut(BaseModel):
    text: str
    language: str | None = "zh"
    duration_seconds: float | None = None
    model: str
    segments: list[SegmentOut] = Field(default_factory=list)
