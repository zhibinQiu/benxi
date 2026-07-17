"""Neo4j 节点/时间通用转换工具。

合并 kg_service.py 和 ontology_service.py 中的重复转换逻辑。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.kg import (
    EntityOut,
    GraphEdgeOut,
    GraphNodeOut,
    RelationOut,
)
from app.schemas.ontology import (
    AxiomOut,
    EntityTypeOut,
    PropertySchema,
    RelationTypeOut,
)


# ── 时间工具 ──────────────────────────────────────────────────


def now() -> datetime:
    """获取当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def neo4j_datetime(val: Any) -> datetime | None:
    """安全地将 Neo4j 返回的时间值转为 Python datetime。

    兼容 Neo4j 原生 datetime 类型和 None。
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return None


# ── 通用 Neo4j 节点提取 ─────────────────────────────────────


def extract_node_props(node: Any) -> dict[str, Any]:
    """提取 Neo4j 节点属性为普通字典。"""
    return dict(node)


# ── PropertySchema 序列化/反序列化 ──────────────────────────


def serialize_property_schema(
    schema: dict[str, PropertySchema],
) -> str:
    """序列化属性模式为 JSON 字符串（Neo4j 不支持嵌套 Map 属性值）。"""
    import json

    return json.dumps(
        {k: v.model_dump() for k, v in schema.items()},
        ensure_ascii=False,
        default=str,
    )


def deserialize_property_schema(
    raw: str | dict[str, Any] | None,
) -> dict[str, PropertySchema]:
    """反序列化属性模式（JSON 字符串或 dict → PropertySchema 字典）。

    兼容旧数据中可能存储为 dict 的情况。
    """
    import json

    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw_dict = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    elif isinstance(raw, dict):
        raw_dict = raw
    else:
        return {}
    result: dict[str, PropertySchema] = {}
    for key, val in raw_dict.items():
        if isinstance(val, dict):
            result[key] = PropertySchema(**val)
        else:
            result[key] = PropertySchema()
    return result


# ── 本体节点 → Pydantic 模型转换（OntologyService 用） ──────


def node_to_entity_type(node: Any) -> EntityTypeOut:
    """Neo4j OntologyEntityType 节点 → EntityTypeOut。"""
    props = extract_node_props(node)
    raw_schema = props.get("property_schema") or {}
    return EntityTypeOut(
        code=props.get("code", ""),
        label=props.get("label", ""),
        color=props.get("color", "blue"),
        icon=props.get("icon", "help-circle"),
        sort_order=props.get("sort_order", 100),
        property_schema=deserialize_property_schema(raw_schema),
        entity_count=0,
        created_at=neo4j_datetime(props.get("created_at")),
        updated_at=neo4j_datetime(props.get("updated_at")),
    )


def node_to_relation_type(node: Any) -> RelationTypeOut:
    """Neo4j OntologyRelationType 节点 → RelationTypeOut。"""
    props = extract_node_props(node)
    return RelationTypeOut(
        code=props.get("code", ""),
        label=props.get("label", ""),
        domain_types=props.get("domain_types") or [],
        range_types=props.get("range_types") or [],
        transitive=bool(props.get("transitive", False)),
        inverse_of=props.get("inverse_of") or None,
        symmetric=bool(props.get("symmetric", False)),
        sort_order=props.get("sort_order", 100),
        relation_count=0,
        created_at=neo4j_datetime(props.get("created_at")),
        updated_at=neo4j_datetime(props.get("updated_at")),
    )


def node_to_axiom(node: Any) -> AxiomOut:
    """Neo4j OntologyAxiom 节点 → AxiomOut。"""
    props = extract_node_props(node)
    return AxiomOut(
        name=props.get("name", ""),
        description=props.get("description", ""),
        cypher_rule=props.get("cypher_rule", ""),
        active=bool(props.get("active", True)),
        last_run_at=neo4j_datetime(props.get("last_run_at")),
        last_run_result=props.get("last_run_result"),
        created_at=neo4j_datetime(props.get("created_at")),
        updated_at=neo4j_datetime(props.get("updated_at")),
    )


# ── KG 实例节点 → Pydantic 模型转换（KgService 用） ────────


def entity_node_to_out(node: Any, et: Any | None = None) -> EntityOut:
    """Neo4j Entity 节点 → EntityOut，附带本体类型信息。"""
    props = extract_node_props(node)
    type_code = props.get("type_code", "")
    type_label = (et.label if et else type_code) if et else type_code
    type_color = (et.color if et else "gray") if et else "gray"

    raw_props = props.get("properties")
    if isinstance(raw_props, str):
        try:
            parsed = json.loads(raw_props)
        except (json.JSONDecodeError, TypeError):
            parsed = {}
    elif isinstance(raw_props, dict):
        parsed = raw_props
    else:
        parsed = {}

    return EntityOut(
        id=props.get("id", ""),
        type_code=type_code,
        type_label=type_label,
        type_color=type_color,
        name=props.get("name", ""),
        description=props.get("description", ""),
        properties=parsed,
        source_type=props.get("source_type", "manual"),
        source_document_id=props.get("source_document_id") or None,
        owner_id=props.get("owner_id", ""),
        created_by=props.get("created_by", ""),
        created_at=neo4j_datetime(props.get("created_at")),
        updated_at=neo4j_datetime(props.get("updated_at")),
    )


def relation_record_to_out(record: Any) -> RelationOut:
    """Neo4j RELATES 关系记录 → RelationOut。

    ``a`` 和 ``b`` 由 Cypher 查询 ``MATCH (a)-[r:RELATES]->(b)`` 直接绑定，
    ``from_entity_id`` / ``to_entity_id`` 取自节点而非关系属性。
    """
    r_dict = extract_node_props(record.get("r", {}))
    a_dict = extract_node_props(record.get("a", {}))
    b_dict = extract_node_props(record.get("b", {}))
    return RelationOut(
        id=r_dict.get("id", ""),
        type_code=r_dict.get("type_code", ""),
        type_label=r_dict.get("type_code", ""),
        from_entity_id=a_dict.get("id", ""),
        from_entity_name=a_dict.get("name", ""),
        from_entity_type=a_dict.get("type_code", ""),
        to_entity_id=b_dict.get("id", ""),
        to_entity_name=b_dict.get("name", ""),
        to_entity_type=b_dict.get("type_code", ""),
        description=r_dict.get("description", ""),
        inferred=bool(r_dict.get("inferred", False)),
        owner_id=r_dict.get("owner_id", ""),
        created_at=neo4j_datetime(r_dict.get("created_at")),
    )


def node_to_graph_node(node: Any) -> GraphNodeOut:
    """Neo4j Entity 节点 → GraphNodeOut（图谱可视化用，不含本体富化）。"""
    nd = extract_node_props(node)
    type_code = nd.get("type_code", "")
    return GraphNodeOut(
        id=nd.get("id", ""),
        name=nd.get("name", ""),
        type_code=type_code,
        type_label=type_code,
        type_color="gray",
    )


def edge_dict_to_graph_edge(ed: dict[str, Any]) -> GraphEdgeOut:
    """关系字典 → GraphEdgeOut。"""
    return GraphEdgeOut(
        id=ed.get("id", ""),
        type_code=ed.get("type_code", ""),
        type_label=ed.get("type_code", ""),
        from_entity_id=ed.get("from_entity_id", ""),
        to_entity_id=ed.get("to_entity_id", ""),
        inferred=bool(ed.get("inferred", False)),
        description=ed.get("description", ""),
    )
