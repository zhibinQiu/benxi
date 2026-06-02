from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    scope: str | None = Field(
        default=None,
        description="限定分级知识库；空表示全部可检索库",
    )

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, value: str | None) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        scope = str(value).strip()
        if scope not in ("company", "department", "team", "personal"):
            raise ValueError("scope 须为 company、department、team 或 personal")
        return scope
    limit: int = Field(default=20, ge=1, le=50)


class KnowledgeSearchHitOut(BaseModel):
    document_id: str
    title: str
    scope: str
    snippet: str
    score: float = 0.0
    source: str = "knowflow"
    anchor_json: dict | None = None


class KnowledgeSearchOut(BaseModel):
    query: str
    hits: list[KnowledgeSearchHitOut]
    knowflow_enabled: bool
    search_mode: str = Field(description="knowflow | local")
