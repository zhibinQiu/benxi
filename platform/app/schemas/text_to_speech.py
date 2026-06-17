from __future__ import annotations

from pydantic import BaseModel, Field


class TtsVoiceOut(BaseModel):
    id: str
    label: str
    gender: str


class TtsMetaOut(BaseModel):
    configured: bool
    provider: str
    model: str
    max_input_chars: int
    supported_formats: list[str]
    default_format: str
    voices: list[TtsVoiceOut]
    emotions: list[dict[str, str]]


class TtsSynthesizeIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice_id: str = "alex"
    emotion: str | None = None
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    response_format: str = "mp3"
