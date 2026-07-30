"""本体定义（Ontology）服务层。

TBox（实体类型、关系类型、公理元数据）存储在 GraphDB，全局共享。
Neo4j 仅用于实例计数、公理 Cypher 执行与传递闭包查询。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.semantic.defaults import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from app.core.graphdb import GraphDbClient, get_graphdb_client
from app.core.neo4j_converter import deserialize_property_schema
from app.ontology.rdf_store import OntologyRdfStore
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
    SchemaGraphOut,
)

logger = logging.getLogger(__name__)


class OntologyService:
    """全局本体定义服务 — GraphDB TBox + Neo4j ABox 辅助。"""

    def __init__(self, graphdb: GraphDbClient, neo4j_driver: AsyncDriver | None = None) -> None:
        self._store = OntologyRdfStore(graphdb)
        self._neo4j = neo4j_driver

    # ── 实体类型 ──────────────────────────────────────────────────────────

    async def set_subclass_of(self, child_code: str, parent_code: str) -> None:
        """写入 rdfs:subClassOf。"""
        await self._store.set_subclass_of(child_code, parent_code)

    async def create_entity_type(self, body: EntityTypeIn) -> EntityTypeOut:
        item = await self._store.create_entity_type(body)
        item.entity_count = await self._count_entities_by_type(body.code)
        return item

    async def list_entity_types(self, *, include_counts: bool = True) -> list[EntityTypeOut]:
        items = await self._store.list_entity_types()
        if not include_counts:
            return items
        counts = await self._count_entities_by_types([i.code for i in items])
        for item in items:
            item.entity_count = counts.get(item.code, 0)
        return items

    async def get_entity_type(self, code: str, *, include_counts: bool = True) -> EntityTypeOut | None:
        item = await self._store.get_entity_type(code)
        if not item:
            return None
        if include_counts:
            item.entity_count = await self._count_entities_by_type(code)
        return item

    async def update_entity_type(self, code: str, body: EntityTypeUpdate) -> EntityTypeOut | None:
        item = await self._store.update_entity_type(code, body)
        if item:
            item.entity_count = await self._count_entities_by_type(code)
        return item

    async def delete_entity_type(self, code: str) -> bool:
        cnt = await self._count_entities_by_type(code)
        if cnt > 0:
            raise ValueError(f"实体类型 '{code}' 下仍有实体，无法删除")
        return await self._store.delete_entity_type(code)

    async def validate_entity_properties(
        self, type_code: str, properties: dict[str, Any], *, name: str = ""
    ) -> list[str]:
        """优先 SHACL 校验，失败时回退 property_schema JSON 规则。"""
        et = await self.get_entity_type(type_code, include_counts=False)
        if not et:
            return [f"实体类型 '{type_code}' 不存在"]
        schema = {
            k: (v.model_dump() if hasattr(v, "model_dump") else v)
            for k, v in (et.property_schema or {}).items()
        }
        try:
            from app.ontology.owl_export import build_shapes_graph_turtle
            from app.ontology.shacl_validate import validate_entity_with_shacl

            shapes_ttl = await build_shapes_graph_turtle(
                self._store._db, class_code=type_code
            )
            return validate_entity_with_shacl(
                shapes_turtle=shapes_ttl,
                type_code=type_code,
                name=name or "",
                properties=properties or {},
                property_schema=schema,
            )
        except Exception as exc:
            logger.warning("SHACL 校验降级: %s", exc)
            errors: list[str] = []
            for key, prop_schema in (et.property_schema or {}).items():
                if prop_schema.required and key not in properties:
                    errors.append(f"缺少必需属性: {key}")
                value = (properties or {}).get(key)
                if value is not None and prop_schema.type == "number":
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors.append(f"属性 '{key}' 需要数值类型")
            return errors

    async def rebuild_shapes_for_all(self) -> dict[str, int]:
        """为全部实体类型重建 DatatypeProperty + SHACL NodeShape。"""
        items = await self.list_entity_types(include_counts=False)
        n = 0
        for et in items:
            schema = {
                k: (v.model_dump() if hasattr(v, "model_dump") else v)
                for k, v in (et.property_schema or {}).items()
            }
            await self._store.sync_owl_shacl_for_class(et.code, schema, label=et.label)
            n += 1
        rels = await self.list_relation_types(include_counts=False)
        for rt in rels:
            await self._store.sync_relation_shape_constraints(
                rt.code, rt.domain_types or [], rt.range_types or []
            )
        return {"entity_shapes": n, "relation_shapes": len(rels)}

    async def export_ttl(self) -> str:
        from app.ontology.owl_export import export_ontology_ttl

        return await export_ontology_ttl(self._store._db)

    async def resolve_or_merge_entity_type(
        self,
        *,
        code: str,
        label: str,
        property_schema: dict | None = None,
        color: str = "blue",
        icon: str = "help-circle",
        sort_order: int = 200,
    ) -> tuple[EntityTypeOut, bool]:
        """解析概念：命中已有则合并 altLabel，否则新建。返回 (类型, created)。"""
        from app.ontology.synonym_merge import (
            builtin_canonical_for_label,
            resolve_concept_against_catalog,
            should_create_new_code,
        )

        existing_list = await self.list_entity_types(include_counts=False)
        catalog = []
        for et in existing_list:
            alts = await self._store.list_alt_labels(et.code)
            catalog.append(
                {"code": et.code, "label": et.label, "alt_labels": alts}
            )

        # 内置同义优先映射到已存在的 canonical
        syn = builtin_canonical_for_label(label) or builtin_canonical_for_label(code)
        if syn:
            et = await self.get_entity_type(syn, include_counts=False)
            if et:
                if label and label != et.label:
                    await self._store.add_alt_label(et.code, label)
                return et, False

        match = resolve_concept_against_catalog(
            code=code, label=label, existing=catalog
        )
        if match:
            et = await self.get_entity_type(match.canonical_code, include_counts=False)
            if et:
                if match.add_alt_label:
                    await self._store.add_alt_label(et.code, match.add_alt_label)
                elif label and label != et.label:
                    await self._store.add_alt_label(et.code, label)
                return et, False

        if not should_create_new_code(code):
            raise ValueError(f"无效的实体类型 code: {code}")

        created = await self.create_entity_type(
            EntityTypeIn(
                code=code,
                label=label or code,
                color=color,
                icon=icon,
                sort_order=sort_order,
                property_schema=property_schema or {},
            )
        )
        return created, True

    async def merge_entity_types(self, source_code: str, target_code: str) -> dict[str, Any]:
        """将 source 概念合并到 target：altLabel、equivalentClass、关系引用改写。"""
        src = await self.get_entity_type(source_code, include_counts=False)
        tgt = await self.get_entity_type(target_code, include_counts=False)
        if not src or not tgt:
            raise ValueError("源或目标实体类型不存在")
        if source_code == target_code:
            raise ValueError("源与目标不能相同")

        await self._store.add_alt_label(target_code, src.label)
        for alt in await self._store.list_alt_labels(source_code):
            await self._store.add_alt_label(target_code, alt)
        await self._store.set_equivalent_class(source_code, target_code)

        # 改写关系 domain/range 中的 source → target
        rels = await self.list_relation_types(include_counts=False)
        rewritten = 0
        for rt in rels:
            domains = list(rt.domain_types or [])
            ranges = list(rt.range_types or [])
            changed = False
            if source_code in domains:
                domains = [target_code if d == source_code else d for d in domains]
                domains = list(dict.fromkeys(domains))
                changed = True
            if source_code in ranges:
                ranges = [target_code if r == source_code else r for r in ranges]
                ranges = list(dict.fromkeys(ranges))
                changed = True
            if changed:
                await self.update_relation_type(
                    rt.code,
                    RelationTypeUpdate(domain_types=domains, range_types=ranges),
                )
                rewritten += 1

        return {
            "source": source_code,
            "target": target_code,
            "relations_rewritten": rewritten,
        }

    # ── 关系类型 ──────────────────────────────────────────────────────────

    async def create_relation_type(self, body: RelationTypeIn) -> RelationTypeOut:
        item = await self._store.create_relation_type(body)
        item.relation_count = await self._count_relations_by_type(body.code)
        return item

    async def list_relation_types(self, *, include_counts: bool = True) -> list[RelationTypeOut]:
        items = await self._store.list_relation_types()
        if not include_counts:
            return items
        counts = await self._count_relations_by_types([i.code for i in items])
        for item in items:
            item.relation_count = counts.get(item.code, 0)
        return items

    async def get_relation_type(self, code: str, *, include_counts: bool = True) -> RelationTypeOut | None:
        item = await self._store.get_relation_type(code)
        if not item:
            return None
        if include_counts:
            item.relation_count = await self._count_relations_by_type(code)
        return item

    async def update_relation_type(self, code: str, body: RelationTypeUpdate) -> RelationTypeOut | None:
        item = await self._store.update_relation_type(code, body)
        if item:
            item.relation_count = await self._count_relations_by_type(code)
        return item

    async def delete_relation_type(self, code: str) -> bool:
        cnt = await self._count_relations_by_type(code)
        if cnt > 0:
            raise ValueError(f"关系类型 '{code}' 仍有实例，无法删除")
        return await self._store.delete_relation_type(code)

    async def validate_relation_domain_range(
        self, type_code: str, from_type: str, to_type: str
    ) -> list[str]:
        rt = await self.get_relation_type(type_code)
        if not rt:
            return [f"关系类型 '{type_code}' 不存在"]
        errors: list[str] = []
        if rt.domain_types and from_type not in rt.domain_types:
            errors.append(
                f"关系 '{type_code}' 的起点类型必须是 {rt.domain_types}，当前为 '{from_type}'"
            )
        if rt.range_types and to_type not in rt.range_types:
            errors.append(
                f"关系 '{type_code}' 的终点类型必须是 {rt.range_types}，当前为 '{to_type}'"
            )
        return errors

    # ── 传递性 / 互逆推理（实例在 Neo4j）────────────────────────────────

    async def resolve_transitive(
        self, type_code: str, from_entity_id: str, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        rt = await self.get_relation_type(type_code)
        if not rt or not rt.transitive or not self._neo4j:
            return []
        depth = max(1, min(int(max_depth), 10))
        async with self._neo4j.session() as s:
            result = await s.run(
                f"""
                MATCH path = (a:Entity {{id: $from_id}})
                             -[:RELATES {{type_code: $type_code}}*1..{depth}]->(b:Entity)
                RETURN b.id AS target_id, b.name AS target_name,
                       b.type_code AS target_type, length(path) AS hops
                """,
                from_id=from_entity_id,
                type_code=type_code,
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
        rts = await self.list_relation_types()
        return {rt.code: rt.inverse_of for rt in rts if rt.inverse_of}

    async def get_transitive_relation_types(self) -> list[str]:
        rts = await self.list_relation_types()
        return [rt.code for rt in rts if rt.transitive]

    # ── 公理（元数据 GraphDB，Cypher 执行 Neo4j）──────────────────────────

    async def create_axiom(self, body: AxiomIn) -> AxiomOut:
        return await self._store.create_axiom(body)

    async def list_axioms(self) -> list[AxiomOut]:
        return await self._store.list_axioms()

    async def get_axiom(self, name: str) -> AxiomOut | None:
        return await self._store.get_axiom(name)

    async def update_axiom(self, name: str, body: AxiomUpdate) -> AxiomOut | None:
        return await self._store.update_axiom(name, body)

    async def delete_axiom(self, name: str) -> bool:
        return await self._store.delete_axiom(name)

    async def run_axiom(self, name: str) -> AxiomRunResult:
        axiom = await self.get_axiom(name)
        if not axiom:
            return AxiomRunResult(name=name, success=False, error="公理不存在")
        if not axiom.active:
            return AxiomRunResult(name=name, success=False, error="公理未启用")
        if not self._neo4j:
            return AxiomRunResult(name=name, success=False, error="Neo4j 不可用")
        try:
            async with self._neo4j.session() as s:
                result = await s.run(axiom.cypher_rule)
                summary = await result.consume()
                affected = summary.counters.properties_set
            await self._store.update_axiom_run_result(
                name, success=True, affected=affected, error=None
            )
            return AxiomRunResult(name=name, success=True, affected_count=affected)
        except Exception as exc:
            error_msg = str(exc)[:500]
            await self._store.update_axiom_run_result(
                name, success=False, affected=None, error=error_msg
            )
            return AxiomRunResult(name=name, success=False, error=error_msg)

    async def run_all_active_axioms(self) -> list[AxiomRunResult]:
        axioms = await self.list_axioms()
        results: list[AxiomRunResult] = []
        for axiom in axioms:
            if axiom.active:
                results.append(await self.run_axiom(axiom.name))
        return results

    # ── 本体概览 / 查询辅助 ───────────────────────────────────────────────

    async def get_schema_graph(self) -> SchemaGraphOut:
        """构建 TBox 可视化图：Class 节点 + subClassOf / ObjectProperty 边。"""
        from app.ontology.constants import type_uri as ontology_type_uri
        from app.schemas.ontology import SchemaGraphEdgeOut, SchemaGraphNodeOut

        # 不查 Neo4j 实例数，避免可视化接口被计数拖慢
        entity_types = await self.list_entity_types(include_counts=False)
        relation_types = await self.list_relation_types(include_counts=False)

        nodes: list[SchemaGraphNodeOut] = []
        edges: list[SchemaGraphEdgeOut] = []
        subclass_count = 0

        for et in entity_types:
            nodes.append(
                SchemaGraphNodeOut(
                    id=et.code,
                    code=et.code,
                    label=et.label,
                    kind="class",
                    type_uri=ontology_type_uri(et.code),
                    color=et.color,
                    icon=et.icon,
                    entity_count=et.entity_count,
                    parent_code=None,
                    property_keys=list((et.property_schema or {}).keys()),
                )
            )

        try:
            subclass_rows = await self._store.list_subclass_edges()
        except Exception:
            subclass_rows = []
        for row in subclass_rows:
            child = str(row.get("child") or "")
            parent = str(row.get("parent") or "")
            if not child or not parent:
                continue
            edges.append(
                SchemaGraphEdgeOut(
                    id=f"sub:{child}->{parent}",
                    source=child,
                    target=parent,
                    kind="subClassOf",
                    label="subClassOf",
                    code="subClassOf",
                )
            )
            subclass_count += 1
            for n in nodes:
                if n.code == child and not n.parent_code:
                    n.parent_code = parent

        for rt in relation_types:
            for src in rt.domain_types or []:
                for dst in rt.range_types or []:
                    edges.append(
                        SchemaGraphEdgeOut(
                            id=f"prop:{rt.code}:{src}->{dst}",
                            source=src,
                            target=dst,
                            kind="property",
                            label=rt.label,
                            code=rt.code,
                            transitive=rt.transitive,
                            symmetric=rt.symmetric,
                        )
                    )

        return SchemaGraphOut(
            nodes=nodes,
            edges=edges,
            class_count=len(nodes),
            property_count=len(relation_types),
            subclass_count=subclass_count,
        )

    async def get_meta(self) -> MetaOut:
        """获取本体概览信息（仅读 GraphDB TBox，不依赖 Neo4j 计数）。"""
        entity_types = await self.list_entity_types(include_counts=False)
        relation_types = await self.list_relation_types(include_counts=False)
        axioms = await self.list_axioms()
        return MetaOut(
            entity_type_count=len(entity_types),
            relation_type_count=len(relation_types),
            axiom_count=len(axioms),
            active_axiom_count=sum(1 for a in axioms if a.active),
            entity_types=entity_types,
            relation_types=relation_types,
        )

    async def compact_schema(
        self,
        question: str = "",
        *,
        type_codes: list[str] | None = None,
        limit_types: int = 12,
    ) -> str:
        """精简 TBox 文本，供 SemanticLayer / kg_query 使用。"""
        entity_types = await self.list_entity_types()
        relation_types = await self.list_relation_types()
        wanted = {c for c in (type_codes or []) if c}
        q = (question or "").strip().lower()
        if q and not wanted:
            for et in entity_types:
                if et.code in q or et.label.lower() in q:
                    wanted.add(et.code)
            if any(k in q for k in ("公司", "部门", "组织", "任职", "成员", "谁")):
                wanted.update({"person", "org"})

        def _keep_et(et: EntityTypeOut) -> bool:
            return not wanted or et.code in wanted

        filtered_et = [et for et in entity_types if _keep_et(et)][:limit_types]
        et_codes = {et.code for et in filtered_et}

        def _keep_rt(rt: RelationTypeOut) -> bool:
            if not wanted:
                return True
            codes = set(rt.domain_types or []) | set(rt.range_types or [])
            if not codes:
                return True
            return bool(codes & et_codes)

        filtered_rt = [rt for rt in relation_types if _keep_rt(rt)][: limit_types * 2]
        lines = ["【本体摘要（相关类型）】", "## 实体类型"]
        for et in filtered_et:
            lines.append(f"- {et.code} ({et.label})")
        lines.append("## 关系类型")
        for rt in filtered_rt:
            domain = f" domain:{rt.domain_types}" if rt.domain_types else ""
            range_ = f" range:{rt.range_types}" if rt.range_types else ""
            trans = " [传递]" if rt.transitive else ""
            inv = f" [互逆:{rt.inverse_of}]" if rt.inverse_of else ""
            lines.append(f"- {rt.code} ({rt.label}){domain}{range_}{trans}{inv}")
        return "\n".join(lines)

    async def get_entity_type_label(self, type_code: str) -> str:
        et = await self.get_entity_type(type_code)
        return et.label if et else type_code

    async def get_relation_type_label(self, type_code: str) -> str:
        code = (type_code or "").removeprefix("inverse_of_")
        rt = await self.get_relation_type(code)
        return rt.label if rt else type_code

    # ── 默认种子 ──────────────────────────────────────────────────────────

    async def seed_defaults(self, overwrite: bool = False) -> dict[str, int]:
        stats: dict[str, int] = {"entity_types_created": 0, "relation_types_created": 0}

        for et_def in DEFAULT_ENTITY_TYPES:
            # 仅查 GraphDB，避免 Neo4j 计数失败阻断种子写入
            existing = await self._store.get_entity_type(et_def["code"])
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
                await self._store.create_entity_type(
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

        for rt_def in DEFAULT_RELATION_TYPES:
            existing = await self._store.get_relation_type(rt_def["code"])
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
                        inverse_of=None,
                        symmetric=rt_def.get("symmetric", False),
                        sort_order=rt_def["sort_order"],
                    ),
                )
            else:
                await self._store.create_relation_type(
                    RelationTypeIn(
                        code=rt_def["code"],
                        label=rt_def["label"],
                        domain_types=rt_def.get("domain_types", []),
                        range_types=rt_def.get("range_types", []),
                        transitive=rt_def.get("transitive", False),
                        inverse_of=None,
                        symmetric=rt_def.get("symmetric", False),
                        sort_order=rt_def["sort_order"],
                    )
                )
                stats["relation_types_created"] += 1

        for rt_def in DEFAULT_RELATION_TYPES:
            inv = rt_def.get("inverse_of")
            if not inv:
                continue
            existing = await self._store.get_relation_type(rt_def["code"])
            if not existing or existing.inverse_of == inv:
                continue
            await self.update_relation_type(rt_def["code"], RelationTypeUpdate(inverse_of=inv))

        logger.info("Ontology defaults seeded: %s", stats)
        # 为已有类型补齐 SHACL（含本次跳过的）
        try:
            shape_stats = await self.rebuild_shapes_for_all()
            stats["shapes_rebuilt"] = shape_stats.get("entity_shapes", 0)
        except Exception as exc:
            logger.warning("种子后 rebuild shapes 失败: %s", exc)
        return stats

    # ── Neo4j 实例计数（全局；失败时降级为 0，不阻断 TBox 读取）────────────

    async def _count_entities_by_type(self, type_code: str) -> int:
        counts = await self._count_entities_by_types([type_code])
        return counts.get(type_code, 0)

    async def _count_entities_by_types(self, codes: list[str]) -> dict[str, int]:
        if not codes or not self._neo4j:
            return {}
        try:
            async def _query() -> dict[str, int]:
                async with self._neo4j.session() as s:
                    result = await s.run(
                        """
                        UNWIND $codes AS code
                        OPTIONAL MATCH (e:Entity {type_code: code})
                        RETURN code, count(e) AS cnt
                        """,
                        codes=codes,
                    )
                    out: dict[str, int] = {}
                    async for record in result:
                        out[str(record["code"])] = int(record.get("cnt") or 0)
                    return out

            return await asyncio.wait_for(_query(), timeout=5.0)
        except Exception as exc:
            logger.warning("Neo4j 实体计数降级为 0: %s", exc)
            return {c: 0 for c in codes}

    async def _count_relations_by_type(self, type_code: str) -> int:
        counts = await self._count_relations_by_types([type_code])
        return counts.get(type_code, 0)

    async def _count_relations_by_types(self, codes: list[str]) -> dict[str, int]:
        if not codes or not self._neo4j:
            return {}
        try:
            async def _query() -> dict[str, int]:
                async with self._neo4j.session() as s:
                    result = await s.run(
                        """
                        UNWIND $codes AS code
                        OPTIONAL MATCH ()-[r:RELATES {type_code: code}]-()
                        RETURN code, count(r) AS cnt
                        """,
                        codes=codes,
                    )
                    out: dict[str, int] = {}
                    async for record in result:
                        out[str(record["code"])] = int(record.get("cnt") or 0)
                    return out

            return await asyncio.wait_for(_query(), timeout=5.0)
        except Exception as exc:
            logger.warning("Neo4j 关系计数降级为 0: %s", exc)
            return {c: 0 for c in codes}


async def get_ontology_service() -> OntologyService:
    """构造全局 OntologyService（GraphDB + Neo4j）。"""
    from app.core.neo4j import get_neo4j

    return OntologyService(get_graphdb_client(), await get_neo4j())
