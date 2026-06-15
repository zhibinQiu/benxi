from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ai_chat import AiChatMessage


class ReportGenerationMetaOut(BaseModel):
    configured: bool
    web_search_enabled: bool
    service_hint: str = ""


class ReportOptimizePresetOut(BaseModel):
    id: str
    label: str
    description: str = ""
    prompt: str


class ReportGenerationChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[AiChatMessage] = Field(default_factory=list, max_length=40)
    conversation_id: str | None = Field(None, max_length=128)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    use_web_search: bool = True


class ReportExportDocxRequest(BaseModel):
    title: str = Field(default="研究报告", min_length=1, max_length=200)
    markdown: str = Field(..., min_length=1, max_length=120000)


class ReportMindmapRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=120000)


class ReportMindmapOut(BaseModel):
    mermaid: str
    source: str = "llm"
