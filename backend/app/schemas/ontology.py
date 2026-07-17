"""本体定义（Ontology）API 数据结构。

本体层（TBox）管理领域知识 Schema，包括：
- 实体类型定义（含属性模式）
- 关系类型定义（含 domain/range、传递性、互逆）
- 公理规则（推理 Cypher）
"""

from __future__ import annotations

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
