"""本体定义（Ontology）服务层。

管理本体层的 CRUD 操作、属性验证、传递闭包解析和公理执行。
所有数据存储在 Neo4j 图数据库中。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.agentkit.graph import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    Neo4jBaseService,
    deserialize_property_schema,
    neo4j_datetime,
    node_to_axiom,
    node_to_entity_type,
    node_to_relation_type,
    now,
    serialize_property_schema,
)
from app.schemas.ontology import (
    AxiomIn,
    AxiomOut,
    AxiomRunResult,
    AxiomUpdate,
    EntityTypeIn,
    EntityTypeOut,
    EntityTypeUpdate,
    MetaOut,
    RelationTypeIn,
    RelationTypeOut,
    RelationTypeUpdate,
)

logger = logging.getLogger(__name__)


class OntologyService(Neo4jBaseService):
    """本体定义服务。

    通过 Neo4j 异步驱动管理本体层（TBox）的实体类型、关系类型和公理。
    """

    def __init__(self, driver: AsyncDriver) -> None:
        super().__init__(driver)

    # ── 实体类型 ──────────────────────────────────────────────────────────

    async def create_entity_type(self, body: EntityTypeIn) -> EntityTypeOut:
        """创建实体类型定义。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                CREATE (et:OntologyEntityType {
                    code: $code, label: $label, color: $color,
                    icon: $icon, sort_order: $sort_order,
                    property_schema: $property_schema,
                    created_at: datetime(), updated_at: datetime()
                })
                RETURN et
                """,
                code=body.code,
                label=body.label,
                color=body.color,
                icon=body.icon,
                sort_order=body.sort_order,
                property_schema=serialize_property_schema(body.property_schema or {}),
            )
            record = await result.single()
            if not record:
                raise ValueError("创建实体类型失败")
            return node_to_entity_type(record["et"])

    async def list_entity_types(self) -> list[EntityTypeOut]:
        """列出所有实体类型，附带实体计数。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (et:OntologyEntityType)
                OPTIONAL MATCH (e:Entity)
                WHERE e.type_code = et.code
                WITH et, count(DISTINCT e) AS entity_count
                RETURN et, entity_count
                ORDER BY et.sort_order, et.code
                """
            )
            items: list[EntityTypeOut] = []
            async for record in result:
                item = node_to_entity_type(record["et"])
                item.entity_count = record.get("entity_count", 0) or 0
                items.append(item)
            return items

    async def get_entity_type(self, code: str) -> EntityTypeOut | None:
        """获取单个实体类型定义。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (et:OntologyEntityType {code: $code})
                OPTIONAL MATCH (e:Entity)
                WHERE e.type_code = et.code
                WITH et, count(DISTINCT e) AS entity_count
                RETURN et, entity_count
                """,
                code=code,
            )
            record = await result.single()
            if not record:
                return None
            item = node_to_entity_type(record["et"])
            item.entity_count = record.get("entity_count", 0) or 0
            return item

    async def update_entity_type(self, code: str, body: EntityTypeUpdate) -> EntityTypeOut | None:
        """更新实体类型定义。"""
        sets: list[str] = []
        params: dict[str, Any] = {"code": code}
        if body.label is not None:
            sets.append("et.label = $label")
            params["label"] = body.label
        if body.color is not None:
            sets.append("et.color = $color")
            params["color"] = body.color
        if body.icon is not None:
            sets.append("et.icon = $icon")
            params["icon"] = body.icon
        if body.sort_order is not None:
            sets.append("et.sort_order = $sort_order")
            params["sort_order"] = body.sort_order
        if body.property_schema is not None:
            sets.append("et.property_schema = $property_schema")
            params["property_schema"] = serialize_property_schema(body.property_schema)
        if not sets:
            return await self.get_entity_type(code)
        sets.append("et.updated_at = datetime()")
        set_clause = ", ".join(sets)
        async with self._driver.session() as s:
            result = await s.run(
                f"""
                MATCH (et:OntologyEntityType {{code: $code}})
                SET {set_clause}
                RETURN et
                """,
                **params,
            )
            record = await result.single()
            if not record:
                return None
            return node_to_entity_type(record["et"])

    async def delete_entity_type(self, code: str) -> bool:
        """删除实体类型定义。"""
        async with self._driver.session() as s:
            check = await s.run(
                "MATCH (e:Entity {type_code: $code}) RETURN count(e) AS cnt",
                code=code,
            )
            record = await check.single()
            if record and (record.get("cnt") or 0) > 0:
                raise ValueError(f"实体类型 '{code}' 下仍有实体，无法删除")

            result = await s.run(
                "MATCH (et:OntologyEntityType {code: $code}) DELETE et RETURN count(et) AS deleted",
                code=code,
            )
            record = await result.single()
            return (record.get("deleted") or 0) > 0

    async def validate_entity_properties(
        self, type_code: str, properties: dict[str, Any]
    ) -> list[str]:
        """验证实体属性是否符合本体定义。"""
        et = await self.get_entity_type(type_code)
        if not et:
            return [f"实体类型 '{type_code}' 不存在"]
        errors: list[str] = []
        for key, prop_schema in (et.property_schema or {}).items():
            if prop_schema.required and key not in properties:
                errors.append(f"缺少必需属性: {key}")
            value = properties.get(key)
            if value is not None and prop_schema.type == "number":
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors.append(f"属性 '{key}' 需要数值类型")
        return errors

    # ── 关系类型 ──────────────────────────────────────────────────────────

    async def create_relation_type(self, body: RelationTypeIn) -> RelationTypeOut:
        """创建关系类型定义。"""
        if body.inverse_of:
            inv = await self.get_relation_type(body.inverse_of)
            if not inv:
                raise ValueError(f"互逆关系类型 '{body.inverse_of}' 不存在")
        async with self._driver.session() as s:
            result = await s.run(
                """
                CREATE (rt:OntologyRelationType {
                    code: $code, label: $label,
                    domain_types: $domain_types, range_types: $range_types,
                    transitive: $transitive, inverse_of: $inverse_of,
                    symmetric: $symmetric, sort_order: $sort_order,
                    created_at: datetime(), updated_at: datetime()
                })
                RETURN rt
                """,
                code=body.code,
                label=body.label,
                domain_types=body.domain_types or [],
                range_types=body.range_types or [],
                transitive=body.transitive,
                inverse_of=body.inverse_of or "",
                symmetric=body.symmetric,
                sort_order=body.sort_order,
            )
            record = await result.single()
            if not record:
                raise ValueError("创建关系类型失败")
            return node_to_relation_type(record["rt"])

    async def list_relation_types(self) -> list[RelationTypeOut]:
        """列出所有关系类型，附带关系计数。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (rt:OntologyRelationType)
                OPTIONAL MATCH ()-[r:RELATES]-()
                WHERE r.type_code = rt.code
                WITH rt, count(DISTINCT r) AS relation_count
                RETURN rt, relation_count
                ORDER BY rt.sort_order, rt.code
                """
            )
            items: list[RelationTypeOut] = []
            async for record in result:
                item = node_to_relation_type(record["rt"])
                item.relation_count = record.get("relation_count", 0) or 0
                items.append(item)
            return items

    async def get_relation_type(self, code: str) -> RelationTypeOut | None:
        """获取单个关系类型定义。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (rt:OntologyRelationType {code: $code})
                OPTIONAL MATCH ()-[r:RELATES]-()
                WHERE r.type_code = rt.code
                WITH rt, count(DISTINCT r) AS relation_count
                RETURN rt, relation_count
                """,
                code=code,
            )
            record = await result.single()
            if not record:
                return None
            item = node_to_relation_type(record["rt"])
            item.relation_count = record.get("relation_count", 0) or 0
            return item

    async def update_relation_type(self, code: str, body: RelationTypeUpdate) -> RelationTypeOut | None:
        """更新关系类型定义。"""
        sets: list[str] = []
        params: dict[str, Any] = {"code": code}
        if body.label is not None:
            sets.append("rt.label = $label")
            params["label"] = body.label
        if body.domain_types is not None:
            sets.append("rt.domain_types = $domain_types")
            params["domain_types"] = body.domain_types
        if body.range_types is not None:
            sets.append("rt.range_types = $range_types")
            params["range_types"] = body.range_types
        if body.transitive is not None:
            sets.append("rt.transitive = $transitive")
            params["transitive"] = body.transitive
        if body.inverse_of is not None:
            sets.append("rt.inverse_of = $inverse_of")
            params["inverse_of"] = body.inverse_of
        if body.symmetric is not None:
            sets.append("rt.symmetric = $symmetric")
            params["symmetric"] = body.symmetric
        if body.sort_order is not None:
            sets.append("rt.sort_order = $sort_order")
            params["sort_order"] = body.sort_order
        if not sets:
            return await self.get_relation_type(code)
        sets.append("rt.updated_at = datetime()")
        set_clause = ", ".join(sets)
        async with self._driver.session() as s:
            result = await s.run(
                f"""
                MATCH (rt:OntologyRelationType {{code: $code}})
                SET {set_clause}
                RETURN rt
                """,
                **params,
            )
            record = await result.single()
            if not record:
                return None
            return node_to_relation_type(record["rt"])

    async def delete_relation_type(self, code: str) -> bool:
        """删除关系类型定义。"""
        async with self._driver.session() as s:
            check = await s.run(
                "MATCH ()-[r:RELATES {type_code: $code}]-() RETURN count(r) AS cnt",
                code=code,
            )
            record = await check.single()
            if record and (record.get("cnt") or 0) > 0:
                raise ValueError(f"关系类型 '{code}' 仍有实例，无法删除")
            result = await s.run(
                "MATCH (rt:OntologyRelationType {code: $code}) DELETE rt RETURN count(rt) AS deleted",
                code=code,
            )
            record = await result.single()
            return (record.get("deleted") or 0) > 0

    async def validate_relation_domain_range(
        self, type_code: str, from_type: str, to_type: str
    ) -> list[str]:
        """验证关系两端的实体类型是否符合 domain/range 约束。"""
        rt = await self.get_relation_type(type_code)
        if not rt:
            return [f"关系类型 '{type_code}' 不存在"]
        errors: list[str] = []
        if rt.domain_types and from_type not in rt.domain_types:
            errors.append(f"关系 '{type_code}' 的起点类型必须是 {rt.domain_types}，当前为 '{from_type}'")
        if rt.range_types and to_type not in rt.range_types:
            errors.append(f"关系 '{type_code}' 的终点类型必须是 {rt.range_types}，当前为 '{to_type}'")
        return errors

    # ── 传递性 / 互逆推理 ─────────────────────────────────────────────────

    async def resolve_transitive(
        self, type_code: str, from_entity_id: str, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        """沿 transitive 关系链展开传递闭包。"""
        rt = await self.get_relation_type(type_code)
        if not rt or not rt.transitive:
            return []
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH path = (a:Entity {id: $from_id})
                             -[:RELATES {type_code: $type_code}*1..$max_depth]->(b:Entity)
                RETURN b.id AS target_id, b.name AS target_name,
                       b.type_code AS target_type, length(path) AS hops
                """,
                from_id=from_entity_id,
                type_code=type_code,
                max_depth=max_depth,
            )
            items: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            async for record in result:
                tid = record.get("target_id")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    items.append(dict(record))
            return items

    async def get_inverse_relation_types(self) -> dict[str, str]:
        """获取所有互逆关系对 {code: inverse_code}。"""
        rts = await self.list_relation_types()
        inverse_map: dict[str, str] = {}
        for rt in rts:
            if rt.inverse_of:
                inverse_map[rt.code] = rt.inverse_of
        return inverse_map

    async def get_transitive_relation_types(self) -> list[str]:
        """获取所有传递关系的 code 列表。"""
        rts = await self.list_relation_types()
        return [rt.code for rt in rts if rt.transitive]

    # ── 公理管理 ──────────────────────────────────────────────────────────

    async def create_axiom(self, body: AxiomIn) -> AxiomOut:
        """创建公理规则。"""
        async with self._driver.session() as s:
            result = await s.run(
                """
                CREATE (a:OntologyAxiom {
                    name: $name, description: $description,
                    cypher_rule: $cypher_rule, active: $active,
                    created_at: datetime(), updated_at: datetime()
                })
                RETURN a
                """,
                name=body.name,
                description=body.description,
                cypher_rule=body.cypher_rule,
                active=body.active,
            )
            record = await result.single()
            if not record:
                raise ValueError("创建公理失败")
            return node_to_axiom(record["a"])

    async def list_axioms(self) -> list[AxiomOut]:
        """列出所有公理规则。"""
        async with self._driver.session() as s:
            result = await s.run(
                "MATCH (a:OntologyAxiom) RETURN a ORDER BY a.name"
            )
            items: list[AxiomOut] = []
            async for record in result:
                items.append(node_to_axiom(record["a"]))
            return items

    async def get_axiom(self, name: str) -> AxiomOut | None:
        """获取单个公理规则。"""
        async with self._driver.session() as s:
            result = await s.run(
                "MATCH (a:OntologyAxiom {name: $name}) RETURN a",
                name=name,
            )
            record = await result.single()
            if not record:
                return None
            return node_to_axiom(record["a"])

    async def update_axiom(self, name: str, body: AxiomUpdate) -> AxiomOut | None:
        """更新公理规则。"""
        sets: list[str] = []
        params: dict[str, Any] = {"name": name}
        if body.description is not None:
            sets.append("a.description = $description")
            params["description"] = body.description
        if body.cypher_rule is not None:
            sets.append("a.cypher_rule = $cypher_rule")
            params["cypher_rule"] = body.cypher_rule
        if body.active is not None:
            sets.append("a.active = $active")
            params["active"] = body.active
        if not sets:
            return await self.get_axiom(name)
        sets.append("a.updated_at = datetime()")
        set_clause = ", ".join(sets)
        async with self._driver.session() as s:
            result = await s.run(
                f"""
                MATCH (a:OntologyAxiom {{name: $name}})
                SET {set_clause}
                RETURN a
                """,
                **params,
            )
            record = await result.single()
            if not record:
                return None
            return node_to_axiom(record["a"])

    async def delete_axiom(self, name: str) -> bool:
        """删除公理规则。"""
        async with self._driver.session() as s:
            result = await s.run(
                "MATCH (a:OntologyAxiom {name: $name}) DELETE a RETURN count(a) AS deleted",
                name=name,
            )
            record = await result.single()
            return (record.get("deleted") or 0) > 0

    async def run_axiom(self, name: str) -> AxiomRunResult:
        """执行指定公理的 Cypher 规则。"""
        axiom = await self.get_axiom(name)
        if not axiom:
            return AxiomRunResult(name=name, success=False, error="公理不存在")
        if not axiom.active:
            return AxiomRunResult(name=name, success=False, error="公理未启用")
        try:
            async with self._driver.session() as s:
                result = await s.run(axiom.cypher_rule)
                summary = await result.consume()
                affected = summary.counters.properties_set
                await s.run(
                    """
                    MATCH (a:OntologyAxiom {name: $name})
                    SET a.last_run_at = datetime(), a.last_run_result = $result
                    """,
                    name=name,
                    result=f"OK, affected={affected}",
                )
            return AxiomRunResult(name=name, success=True, affected_count=affected)
        except Exception as exc:
            error_msg = str(exc)[:500]
            async with self._driver.session() as s:
                await s.run(
                    """
                    MATCH (a:OntologyAxiom {name: $name})
                    SET a.last_run_at = datetime(), a.last_run_result = $result
                    """,
                    name=name,
                    result=f"ERROR: {error_msg}",
                )
            return AxiomRunResult(name=name, success=False, error=error_msg)

    async def run_all_active_axioms(self) -> list[AxiomRunResult]:
        """执行所有活跃公理。"""
        axioms = await self.list_axioms()
        results: list[AxiomRunResult] = []
        for axiom in axioms:
            if axiom.active:
                result = await self.run_axiom(axiom.name)
                results.append(result)
        return results

    # ── 本体概览 ──────────────────────────────────────────────────────────

    async def get_meta(self) -> MetaOut:
        """获取本体概览信息。"""
        entity_types = await self.list_entity_types()
        relation_types = await self.list_relation_types()
        axioms = await self.list_axioms()
        return MetaOut(
            entity_type_count=len(entity_types),
            relation_type_count=len(relation_types),
            axiom_count=len(axioms),
            active_axiom_count=sum(1 for a in axioms if a.active),
            entity_types=entity_types,
            relation_types=relation_types,
        )

    # ── 默认种子 ──────────────────────────────────────────────────────────

    async def seed_defaults(self, overwrite: bool = False) -> dict[str, int]:
        """初始化默认本体（实体类型和关系类型）。"""
        stats: dict[str, int] = {"entity_types_created": 0, "relation_types_created": 0}

        for et_def in DEFAULT_ENTITY_TYPES:
            existing = await self.get_entity_type(et_def["code"])
            if existing and not overwrite:
                continue
            prop_schema = deserialize_property_schema(et_def.get("property_schema", {}))
            if existing and overwrite:
                await self.update_entity_type(
                    et_def["code"],
                    EntityTypeUpdate(
                        label=et_def["label"],
                        color=et_def["color"],
                        icon=et_def.get("icon", "help-circle"),
                        sort_order=et_def["sort_order"],
                        property_schema=prop_schema,
                    ),
                )
            else:
                await self.create_entity_type(
                    EntityTypeIn(
                        code=et_def["code"],
                        label=et_def["label"],
                        color=et_def["color"],
                        icon=et_def.get("icon", "help-circle"),
                        sort_order=et_def["sort_order"],
                        property_schema=prop_schema,
                    )
                )
                stats["entity_types_created"] += 1

        # 两遍创建：先创建所有关系类型（不含 inverse_of），再设置互逆关系
        created_rt_codes: list[str] = []
        for rt_def in DEFAULT_RELATION_TYPES:
            existing = await self.get_relation_type(rt_def["code"])
            if existing and not overwrite:
                continue
            if existing and overwrite:
                await self.update_relation_type(
                    rt_def["code"],
                    RelationTypeUpdate(
                        label=rt_def["label"],
                        domain_types=rt_def.get("domain_types", []),
                        range_types=rt_def.get("range_types", []),
                        transitive=rt_def.get("transitive", False),
                        inverse_of=None,  # 第二遍再设置
                        symmetric=rt_def.get("symmetric", False),
                        sort_order=rt_def["sort_order"],
                    ),
                )
            else:
                await self.create_relation_type(
                    RelationTypeIn(
                        code=rt_def["code"],
                        label=rt_def["label"],
                        domain_types=rt_def.get("domain_types", []),
                        range_types=rt_def.get("range_types", []),
                        transitive=rt_def.get("transitive", False),
                        inverse_of=None,  # 第二遍再设置
                        symmetric=rt_def.get("symmetric", False),
                        sort_order=rt_def["sort_order"],
                    )
                )
                created_rt_codes.append(rt_def["code"])
            stats["relation_types_created"] += 1

        # 第二遍：为已存在的关系设置互逆关系
        for rt_def in DEFAULT_RELATION_TYPES:
            inv = rt_def.get("inverse_of")
            if not inv:
                continue
            existing = await self.get_relation_type(rt_def["code"])
            if not existing:
                continue
            if existing.inverse_of == inv:
                continue
            await self.update_relation_type(
                rt_def["code"],
                RelationTypeUpdate(inverse_of=inv),
            )

        logger.info("Ontology defaults seeded: %s", stats)
        return stats
