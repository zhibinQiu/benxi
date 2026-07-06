from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class OcrBlockOut(BaseModel):
    text: str
    page: int = 1
    bbox: list[float] | None = None
    block_type: str = "text"


class OcrPageOut(BaseModel):
    page: int
    text: str
    blocks: list[OcrBlockOut] = Field(default_factory=list)


class OcrMetaOut(BaseModel):
    configured: bool
    provider: str
    model: str
    max_file_mb: int
    accepted_extensions: list[str]
    default_language: str | None = None
    service_hint: str | None = None


class OcrRecognizeOut(BaseModel):
    file_name: str
    text: str
    markdown: str
    blocks: list[OcrBlockOut] = Field(default_factory=list)
    pages: list[OcrPageOut] = Field(default_factory=list)
    model: str
    provider: str


class OcrExportItemIn(BaseModel):
    file_name: str
    text: str = ""
    markdown: str = ""
    blocks: list[OcrBlockOut] = Field(default_factory=list)
    pages: list[OcrPageOut] = Field(default_factory=list)


class OcrExportIn(BaseModel):
    format: Literal["markdown", "json"] = "markdown"
    items: list[OcrExportItemIn] = Field(..., min_length=1)


class OcrExportJsonDocument(BaseModel):
    file_name: str
    text: str
    pages: list[OcrPageOut]
    blocks: list[OcrBlockOut]
    meta: dict[str, Any] = Field(default_factory=dict)
