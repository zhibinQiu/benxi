"""Document compare API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompareDocumentOut(BaseModel):
    id: str
    title: str
    file_name: str
    file_size: int
    updated_at: str | None = None


class CompareJobCreate(BaseModel):
    left_document_id: str = Field(..., description="左侧：待比对文档")
    right_document_id: str = Field(..., description="右侧：比对目标")


class CompareSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    scope: str = Field(
        "right",
        description="检索范围：right（仅右侧）、both（两侧）",
    )
    field_match: bool = Field(
        True, description="启用字段匹配，如 条款:违约金",
    )


class CompareDirectSearchRequest(BaseModel):
    """无需段落比对任务，直接在右侧目标文档内检索。"""

    right_document_id: str = Field(..., description="右侧：检索目标文档")
    query: str = Field(..., min_length=1, max_length=500)
    field_match: bool = Field(
        True, description="KnowFlow 不可用时的本地字段匹配",
    )


class CompareSearchHitOut(BaseModel):
    id: str | None = None
    document_id: str
    snippet: str
    score: float
    anchor_json: dict | None = None
    source: str = "local"


class CompareDiffItemOut(BaseModel):
    id: str
    diff_type: str
    text_left: str | None = None
    text_right: str | None = None
    anchor_json: dict | None = None


class CompareJobOut(BaseModel):
    id: str
    status: str
    progress: int
    error_message: str | None = None
    left_document_id: str
    right_document_id: str
    document_titles: dict[str, str]
    payload: dict | None = None
    diff_items: list[CompareDiffItemOut] = []
    created_at: str | None = None
    finished_at: str | None = None
