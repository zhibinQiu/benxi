"""业务概念属性 ↔ 事实数据源字段映射。"""

from __future__ import annotations

from typing import Any

from app.semantic.defaults import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from app.semantic.models import FieldBinding, ResolvedConcept
from app.semantic.ontology.sql_registry import (
    SqlBindingRegistry,
    get_sql_binding_registry,
)

# Re-export registry helpers for callers that historically imported from here
from app.semantic.ontology.sql_registry import (  # noqa: F401
    allowed_columns_for_table,
    executable_sql_tables,
    join_template_columns,
    name_columns_for_table,
    registered_join_templates,
)


class FieldMapper:
    """概念属性 → neo4j / sql / document 绑定（SQL 映射优先读库）。"""

    def __init__(
        self,
        sql_bindings: dict[tuple[str, str], tuple[str, str, str]] | None = None,
        sql_join_bindings: dict[tuple[str, str], tuple[str, str]] | None = None,
        registry: SqlBindingRegistry | None = None,
    ) -> None:
        reg = registry or get_sql_binding_registry()
        self._registry = reg
        self._sql = dict(sql_bindings if sql_bindings is not None else reg.sql_bindings)
        self._sql_joins = dict(
            sql_join_bindings if sql_join_bindings is not None else reg.sql_join_bindings
        )
        self._neo4j_props = self._build_neo4j_prop_index()

    @staticmethod
    def _build_neo4j_prop_index() -> dict[tuple[str, str], str]:
        out: dict[tuple[str, str], str] = {}
        for et in DEFAULT_ENTITY_TYPES:
            code = str(et.get("code") or "")
            schema = et.get("property_schema") or {}
            if not isinstance(schema, dict):
                continue
            for key in schema:
                out[(code, str(key))] = str(key)
        return out

    @staticmethod
    def expand_concepts_via_relations(
        concepts: list[ResolvedConcept],
    ) -> list[ResolvedConcept]:
        """按本体关系 domain/range 补全对端概念（通用，非问句特化）。"""
        if not concepts:
            return []
        by_code = {c.type_code: c for c in concepts if c.type_code}
        added: list[ResolvedConcept] = []
        for c in list(concepts):
            for rt in DEFAULT_RELATION_TYPES:
                code = str(rt.get("code") or "")
                domains = [str(x) for x in (rt.get("domain_types") or [])]
                ranges = [str(x) for x in (rt.get("range_types") or [])]
                peers: list[str] = []
                if c.type_code in domains:
                    peers.extend(ranges)
                if c.type_code in ranges:
                    peers.extend(domains)
                for peer in peers:
                    if not peer or peer in by_code:
                        continue
                    label = next(
                        (
                            str(et.get("label") or peer)
                            for et in DEFAULT_ENTITY_TYPES
                            if str(et.get("code")) == peer
                        ),
                        peer,
                    )
                    nc = ResolvedConcept(
                        type_code=peer,
                        label=label,
                        property_keys=[],
                        relation_codes=[code] if code else [],
                        aliases_hit=[],
                        confidence=0.55,
                        rationale=f"由关系 {code or '?'} 从 {c.type_code} 扩展",
                    )
                    by_code[peer] = nc
                    added.append(nc)
        return [*concepts, *added]

    def map_concepts(self, concepts: list[ResolvedConcept]) -> list[FieldBinding]:
        bindings: list[FieldBinding] = []
        seen: set[tuple[str, str, str]] = set()
        table_cols = self._registry.table_columns
        join_cols = self._registry.join_template_columns
        doc_bindings = self._registry.doc_bindings
        for c in concepts or []:
            keys = list(c.property_keys)
            if not keys:
                keys = [k for (code, k) in self._neo4j_props if code == c.type_code]
                for (code, prop) in self._sql_joins:
                    if code == c.type_code and prop not in keys:
                        keys.append(prop)
            if not keys:
                if (c.type_code, "*", "neo4j") not in seen:
                    bindings.append(
                        FieldBinding(
                            concept=c.type_code,
                            property_key="*",
                            source="neo4j",
                            neo4j_prop="Entity",
                            notes=f"实例存 Neo4j Entity.type_code={c.type_code}",
                        )
                    )
                    seen.add((c.type_code, "*", "neo4j"))
                continue
            for prop in keys:
                sql = self._sql.get((c.type_code, prop))
                join = self._sql_joins.get((c.type_code, prop))
                has_sql = False
                if sql and (c.type_code, prop, "sql") not in seen:
                    table, column, notes = sql
                    if table in table_cols and column in table_cols[table]:
                        bindings.append(
                            FieldBinding(
                                concept=c.type_code,
                                property_key=prop,
                                source="sql",
                                table=table,
                                column=column,
                                notes=notes,
                            )
                        )
                        seen.add((c.type_code, prop, "sql"))
                        has_sql = True

                if join and (c.type_code, prop, "sql_join") not in seen:
                    template_id, notes = join
                    if template_id in join_cols:
                        bindings.append(
                            FieldBinding(
                                concept=c.type_code,
                                property_key=prop,
                                source="sql",
                                join_template=template_id,
                                notes=notes,
                            )
                        )
                        seen.add((c.type_code, prop, "sql_join"))
                        has_sql = True

                if (
                    not has_sql
                    and (c.type_code, prop) in self._neo4j_props
                    and (c.type_code, prop, "neo4j") not in seen
                ):
                    bindings.append(
                        FieldBinding(
                            concept=c.type_code,
                            property_key=prop,
                            source="neo4j",
                            neo4j_prop=self._neo4j_props[(c.type_code, prop)],
                            notes="图谱关键标识/实体属性",
                        )
                    )
                    seen.add((c.type_code, prop, "neo4j"))

                doc_note = doc_bindings.get((c.type_code, prop))
                if doc_note and (c.type_code, prop, "document") not in seen:
                    bindings.append(
                        FieldBinding(
                            concept=c.type_code,
                            property_key=prop,
                            source="document",
                            notes=doc_note,
                        )
                    )
                    seen.add((c.type_code, prop, "document"))
        return bindings
