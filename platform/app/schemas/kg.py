"""知识图谱 API 结构。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class KgEntityTypeOut(BaseModel):
    id: UUID
    code: str
    label: str
    color: str
    description: str
    sort_order: int
    entity_count: int = 0


class KgRelationTypeOut(BaseModel):
    id: UUID
    code: str
    label: str
    description: str
    sort_order: int
    relation_count: int = 0


class KgEntityTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    color: str = Field(default="blue", max_length=32)
    description: str = ""
    sort_order: int = 100


class KgEntityTypeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    description: str | None = None
    sort_order: int | None = None


class KgRelationTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    description: str = ""
    sort_order: int = 100


class KgRelationTypeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = None


class KgEntityOut(BaseModel):
    id: UUID
    type_id: UUID
    type_code: str
    type_label: str
    type_color: str
    name: str
    description: str
    properties: dict[str, Any]
    scope: str
    created_at: datetime
    updated_at: datetime


class KgEntityIn(BaseModel):
    type_id: UUID
    name: str = Field(min_length=1, max_length=256)
    description: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class KgEntityUpdate(BaseModel):
    type_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    properties: dict[str, Any] | None = None


class KgRelationOut(BaseModel):
    id: UUID
    relation_type_id: UUID
    relation_type_code: str
    relation_type_label: str
    from_entity_id: UUID
    to_entity_id: UUID
    from_name: str
    to_name: str
    description: str
    created_at: datetime


class KgRelationIn(BaseModel):
    relation_type_id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    description: str = ""


class KgGraphNodeOut(BaseModel):
    id: UUID
    name: str
    type_code: str
    type_label: str
    type_color: str


class KgGraphEdgeOut(BaseModel):
    id: UUID
    relation_type_code: str
    relation_type_label: str
    from_entity_id: UUID
    to_entity_id: UUID


class KgGraphOut(BaseModel):
    nodes: list[KgGraphNodeOut]
    edges: list[KgGraphEdgeOut]
    focus_entity_id: UUID | None = None


class KgMetaOut(BaseModel):
    entity_types: list[KgEntityTypeOut]
    relation_types: list[KgRelationTypeOut]
    entity_total: int
    relation_total: int
