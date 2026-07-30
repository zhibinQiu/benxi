"""本体定义（Ontology）API 数据结构。

本体层（TBox）存 GraphDB，全局共享；实例层（ABox）存 Neo4j。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PropertySchema(BaseModel):
    """属性模式定义 — 描述实体类型的某个属性。"""

    type: str = Field(
        default="string",
        pattern="^(string|number|date|boolean|text|url)$",
        description="属性类型：string / number / date / boolean / text / url",
    )
    required: bool = False
    description: str = ""
    default_value: Any | None = None


class EntityTypeOut(BaseModel):
    """实体类型定义（本体层）。"""

    code: str
    label: str
    color: str
    icon: str
    sort_order: int
    property_schema: dict[str, PropertySchema] = {}
    entity_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EntityTypeIn(BaseModel):
    """创建实体类型的输入。"""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern="^[a-z][a-z0-9_]*$",
        description="唯一标识（小写字母、数字、下划线）",
    )
    label: str = Field(min_length=1, max_length=128)
    color: str = Field(default="blue", max_length=32)
    icon: str = Field(default="help-circle", max_length=64)
    sort_order: int = 100
    property_schema: dict[str, PropertySchema] = Field(
        default_factory=dict,
        description="属性模式字典：key 为属性名，value 为 PropertySchema",
    )


class EntityTypeUpdate(BaseModel):
    """更新实体类型的输入。"""

    label: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None
    property_schema: dict[str, PropertySchema] | None = None


class ValidateInput(BaseModel):
    """属性验证输入。"""

    properties: dict[str, Any] = Field(default_factory=dict)


class ValidateOutput(BaseModel):
    """属性验证输出。"""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RelationTypeOut(BaseModel):
    """关系类型定义（本体层）。"""

    code: str
    label: str
    domain_types: list[str] = []
    range_types: list[str] = []
    transitive: bool = False
    inverse_of: str | None = None
    symmetric: bool = False
    sort_order: int = 100
    relation_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RelationTypeIn(BaseModel):
    """创建关系类型的输入。"""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern="^[a-z][a-z0-9_]*$",
        description="唯一标识（小写字母、数字、下划线）",
    )
    label: str = Field(min_length=1, max_length=128)
    domain_types: list[str] = Field(
        default_factory=list,
        description="可作起点的实体类型 code 列表（空表示不限制）",
    )
    range_types: list[str] = Field(
        default_factory=list,
        description="可作终点的实体类型 code 列表（空表示不限制）",
    )
    transitive: bool = False
    inverse_of: str | None = Field(
        default=None,
        description="互逆关系 type_code（需先存在）",
    )
    symmetric: bool = False
    sort_order: int = 100


class RelationTypeUpdate(BaseModel):
    """更新关系类型的输入。"""

    label: str | None = Field(default=None, min_length=1, max_length=128)
    domain_types: list[str] | None = None
    range_types: list[str] | None = None
    transitive: bool | None = None
    inverse_of: str | None = None
    symmetric: bool | None = None
    sort_order: int | None = None


class AxiomOut(BaseModel):
    """公理规则定义。"""

    name: str
    description: str = ""
    cypher_rule: str
    active: bool = True
    last_run_at: datetime | None = None
    last_run_result: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AxiomIn(BaseModel):
    """创建公理的输入。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    cypher_rule: str = Field(min_length=1, description="可执行的 Cypher 查询语句")
    active: bool = True


class AxiomUpdate(BaseModel):
    """更新公理的输入。"""

    description: str | None = None
    cypher_rule: str | None = Field(
        default=None, min_length=1, description="可执行的 Cypher 查询语句"
    )
    active: bool | None = None


class AxiomRunResult(BaseModel):
    """公理执行结果。"""

    name: str
    success: bool
    affected_count: int | None = None
    error: str | None = None


class MetaOut(BaseModel):
    """本体概览。"""

    entity_type_count: int = 0
    relation_type_count: int = 0
    axiom_count: int = 0
    active_axiom_count: int = 0
    entity_types: list[EntityTypeOut] = []
    relation_types: list[RelationTypeOut] = []


class DefaultSeedIn(BaseModel):
    """初始化默认本体的输入。"""

    confirm: bool = Field(default=False, description="确认初始化")


class MergeTypesIn(BaseModel):
    """合并两个实体类型（source → target）。"""

    source_code: str = Field(min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    target_code: str = Field(min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")


class SchemaGraphNodeOut(BaseModel):
    """语义模型可视化节点（Class / Property）。"""

    id: str
    code: str
    label: str
    kind: str = Field(description="class | property")
    type_uri: str = ""
    color: str = "blue"
    icon: str = "help-circle"
    entity_count: int = 0
    parent_code: str | None = None
    property_keys: list[str] = Field(default_factory=list)


class SchemaGraphEdgeOut(BaseModel):
    """语义模型可视化边（subClassOf / objectProperty）。"""

    id: str
    source: str
    target: str
    kind: str = Field(description="subClassOf | property")
    label: str = ""
    code: str = ""
    transitive: bool = False
    symmetric: bool = False


class SchemaGraphOut(BaseModel):
    """本体 TBox 可视化图（供前端 ECharts Graph）。"""

    nodes: list[SchemaGraphNodeOut] = Field(default_factory=list)
    edges: list[SchemaGraphEdgeOut] = Field(default_factory=list)
    class_count: int = 0
    property_count: int = 0
    subclass_count: int = 0


# ── LLM TBox 发现 ──────────────────────────────────────────────────────────


class OntologyDiscoverFromTextIn(BaseModel):
    """从文本发现本体候选（不写库）。"""

    text: str = Field(min_length=1, description="文档/资料正文")
    title: str = Field(default="文档抽取", max_length=200)
    max_chars: int | None = Field(default=None, ge=2000, le=200000)


class OntologyDiscoverFromDocumentsIn(BaseModel):
    """从平台文档发现本体候选（不写库）。"""

    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    max_chars: int | None = Field(default=None, ge=2000, le=200000)


class OntologyDiscoverPropertyIn(BaseModel):
    name: str = ""
    type: str = "string"
    required: bool = False
    description: str = ""


class OntologyDiscoverEntityCandidate(BaseModel):
    code: str
    label: str
    description: str = ""
    parent_code: str | None = None
    properties: list[OntologyDiscoverPropertyIn] = Field(default_factory=list)
    action: str = Field(description="create | merge | exists")
    merge_into: str | None = None
    note: str = ""
    selected: bool = True


class OntologyDiscoverRelationCandidate(BaseModel):
    code: str
    label: str
    domain_types: list[str] = Field(default_factory=list)
    range_types: list[str] = Field(default_factory=list)
    transitive: bool = False
    symmetric: bool = False
    action: str = Field(description="create | exists")
    note: str = ""
    selected: bool = True


class OntologyDiscoverSkipped(BaseModel):
    kind: str = ""
    code: str = ""
    label: str = ""
    reason: str = ""


class OntologyDiscoverResultOut(BaseModel):
    entity_types: list[OntologyDiscoverEntityCandidate] = Field(default_factory=list)
    relation_types: list[OntologyDiscoverRelationCandidate] = Field(
        default_factory=list
    )
    skipped: list[OntologyDiscoverSkipped] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    document_count: int | None = None
    titles: list[str] = Field(default_factory=list)


class OntologyDiscoverApplyIn(BaseModel):
    """将勾选候选写入 GraphDB。"""

    entity_types: list[OntologyDiscoverEntityCandidate] = Field(default_factory=list)
    relation_types: list[OntologyDiscoverRelationCandidate] = Field(
        default_factory=list
    )


class FieldBindingOut(BaseModel):
    """问数映射：概念属性 → 表列（非 TBox）。"""

    id: str = ""
    concept: str
    property_key: str
    source: str = "sql"
    table_name: str = ""
    column_name: str = ""
    join_template: str = ""
    notes: str = ""
    confidence: float = 1.0
    origin: str = "auto"
    enabled: bool = True
    status: str = "active"


class FieldBindingUpsert(BaseModel):
    concept: str = Field(min_length=1, max_length=64)
    property_key: str = Field(min_length=1, max_length=64)
    source: str = "sql"
    table_name: str = ""
    column_name: str = ""
    join_template: str = ""
    notes: str = ""
    enabled: bool = True
    status: str = "active"


class FieldBindingUpdate(BaseModel):
    table_name: str | None = None
    column_name: str | None = None
    join_template: str | None = None
    notes: str | None = None
    enabled: bool | None = None
    status: str | None = None


class FieldBindingDiscoverOut(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    total: int = 0
    items: list[FieldBindingOut] = Field(default_factory=list)


class FieldBindingSchemaOut(BaseModel):
    """受控 SQL 可编辑的表白名单与列。"""

    tables: dict[str, list[str]] = Field(default_factory=dict)
    join_templates: list[str] = Field(default_factory=list)
