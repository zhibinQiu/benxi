"""单文档版本对比 API schemas。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VersionCompareDiffItemOut(BaseModel):
    id: str
    diff_type: str
    text_left: str | None = None
    text_right: str | None = None
    anchor_json: dict | None = None
    from_version_id: str
    to_version_id: str


class VersionCompareRelationOut(BaseModel):
    id: str
    document_id: str
    from_version_id: str
    to_version_id: str
    from_version_no: int | None = None
    to_version_no: int | None = None
    relation_type: str
    status: str
    progress: int
    diff_count: int
    error_message: str | None = None
    payload: dict | None = None
    created_at: str | None = None
    finished_at: str | None = None
    llm_summary: str | None = None
    llm_summary_status: str | None = None
    precomputed: bool = False
    to_change_description: str = ""
    diff_items: list[VersionCompareDiffItemOut] = Field(default_factory=list)


class VersionCompareBatchIn(BaseModel):
    version_ids: list[str] = Field(min_length=2)


class VersionCompareAskIn(BaseModel):
    left_version_id: str
    right_version_id: str
    question: str = Field(min_length=1)
