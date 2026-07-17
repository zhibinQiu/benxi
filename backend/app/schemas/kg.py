"""知识图谱（KG）API 数据结构。

实例层（ABox）管理具体实体/关系实例，通过本体层（Ontology）约束。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EntityOut(BaseModel):
    """实体实例输出。"""

    id: str
    type_code: str
    type_label: str = ""
    type_color: str = "gray"
    name: str
    description: str = ""
    properties: dict[str, Any] = {}
    source_type: str = "manual"
    source_document_id: str | None = None
    owner_id: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EntityIn(BaseModel):
    """创建实体的输入。"""

    type_code: str = Field(
        min_length=1,
        max_length=64,
        description="实体类型 code（需存在于 ontology）",
    )
    name: str = Field(min_length=1, max_length=256)
    description: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    source_type: str = Field(default="manual", pattern="^(manual|extraction)$")
    source_document_id: str | None = None


class EntityUpdate(BaseModel):
    """更新实体的输入。"""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    type_code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    properties: dict[str, Any] | None = None


class RelationOut(BaseModel):
    """关系实例输出。"""

    id: str
    type_code: str
    type_label: str = ""
    from_entity_id: str
    from_entity_name: str = ""
    from_entity_type: str = ""
    to_entity_id: str
    to_entity_name: str = ""
    to_entity_type: str = ""
    description: str = ""
    inferred: bool = False
    owner_id: str = ""
    created_at: datetime | None = None


class RelationIn(BaseModel):
    """创建关系的输入。"""

    type_code: str = Field(
        min_length=1,
        max_length=64,
        description="关系类型 code（需存在于 ontology）",
    )
    from_entity_id: str = Field(min_length=1)
    to_entity_id: str = Field(min_length=1)
    description: str = ""


class RelationUpdate(BaseModel):
    """更新关系的输入。"""

    type_code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None


class GraphNodeOut(BaseModel):
    """图谱可视化节点。"""

    id: str
    name: str
    type_code: str
    type_label: str = ""
    type_color: str = "gray"


class GraphEdgeOut(BaseModel):
    """图谱可视化边。"""

    id: str
    type_code: str
    type_label: str = ""
    from_entity_id: str
    to_entity_id: str
    inferred: bool = False
    description: str = ""


class GraphOut(BaseModel):
    """图谱可视化输出。"""

    nodes: list[GraphNodeOut] = []
    edges: list[GraphEdgeOut] = []
    focus_entity_id: str | None = None


class GraphReasonIn(BaseModel):
    """推理查询输入。"""

    question: str = Field(min_length=1, description="自然语言问题")
    depth: int = Field(default=3, ge=1, le=5)
    include_inferred: bool = True


class ExtractFromTextIn(BaseModel):
    """从文本抽取实体关系的输入。"""

    title: str = Field(default="未命名", max_length=256)
    text: str = Field(min_length=1)
    source_type: str = Field(default="manual", max_length=64)
    source_id: str | None = None


class ExtractFromTextOut(BaseModel):
    """文本抽取结果输出。"""

    skipped: bool = False
    reason: str | None = None
    entities_created: int = 0
    relations_created: int = 0
    validation_errors: list[str] = []


class ExtractBatchIn(BaseModel):
    """批量抽取输入。"""

    scope: str = Field(
        default="knowledge",
        pattern="^(knowledge|platform)$",
    )
    force: bool = False
    max_docs: int = Field(default=20, ge=1, le=100, description="最大处理文档数")


class ExtractBatchOut(BaseModel):
    """批量抽取结果输出。"""

    queued: bool = False
    reason: str | None = None
    document_count: int = 0
    total_candidates: int = 0


class KgQaContext(BaseModel):
    """图谱问答上下文。"""

    context_text: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    matched_entity_ids: list[str] = Field(default_factory=list)
    entity_count: int = 0
    relation_count: int = 0
    reasoning_hops: int = 0
    inferred_entities: int = 0


class MetaOut(BaseModel):
    """知识图谱概览。"""

    entity_total: int = 0
    relation_total: int = 0
    entity_type_counts: dict[str, int] = {}
    relation_type_counts: dict[str, int] = {}


class ClearOut(BaseModel):
    """清除图谱的输出。"""

    deleted_entities: int = 0
    deleted_relations: int = 0
