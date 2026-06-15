"""PageIndex 实验性检索 API 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageindexMetaOut(BaseModel):
    enabled: bool
    package_available: bool
    llm_configured: bool
    workspace_dir: str
    supported_formats: list[str] = Field(default_factory=list)
    hint: str | None = None


class PageindexSearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1, max_length=5)


class PageindexCitationOut(BaseModel):
    index: int
    document_id: str
    document_title: str
    node_id: str | None = None
    title: str | None = None
    page: int | None = None
    snippet: str | None = None


class PageindexSearchOut(BaseModel):
    answer: str
    thinking: str | None = None
    retrieval_mode: str = "pageindex_tree"
    citations: list[PageindexCitationOut] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
