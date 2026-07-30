"""GraphDB 本体 RDF 读写层。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.neo4j_converter import deserialize_property_schema, serialize_property_schema
from app.core.graphdb import GraphDbClient
from app.ontology.constants import BX_NS, BXMETA_NS, axiom_uri, shape_uri, type_uri
from app.ontology.shacl_shapes import (
    SHACL_PREFIXES,
    build_datatype_properties_insert,
    build_node_shape_insert,
    build_relation_shape_fragment,
)
from app.schemas.ontology import (
    AxiomIn,
    AxiomOut,
    AxiomUpdate,
    EntityTypeIn,
    EntityTypeOut,
    EntityTypeUpdate,
    RelationTypeIn,
    RelationTypeOut,
    RelationTypeUpdate,
)

_PREFIXES = f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX bx: <{BX_NS}>
PREFIX bxmeta: <{BXMETA_NS}>
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sparql_str(val: str) -> str:
    return json.dumps(val, ensure_ascii=False)


def _parse_bool(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1")


def _parse_int(val: Any, default: int = 100) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class OntologyRdfStore:
    """全局本体 TBox 的 GraphDB 持久化。"""

    def __init__(self, client: GraphDbClient) -> None:
        self._db = client

    # ── 实体类型 ──────────────────────────────────────────────────────────

    async def create_entity_type(self, body: EntityTypeIn) -> EntityTypeOut:
        uri = type_uri(body.code)
        if await self._entity_type_exists(body.code):
            raise ValueError(f"实体类型 '{body.code}' 已存在")
        schema_json = serialize_property_schema(body.property_schema or {})
        now = _now_iso()
        update = f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> a owl:Class ;
    bxmeta:code {_sparql_str(body.code)} ;
    rdfs:label {_sparql_str(body.label)} ;
    bxmeta:color {_sparql_str(body.color)} ;
    bxmeta:icon {_sparql_str(body.icon)} ;
    bxmeta:sortOrder "{body.sort_order}"^^xsd:integer ;
    bxmeta:propertySchema {_sparql_str(schema_json)} ;
    bxmeta:createdAt {_sparql_str(now)} ;
    bxmeta:updatedAt {_sparql_str(now)} .
}}
"""
        await self._db.update(update)
        await self.sync_owl_shacl_for_class(
            body.code, body.property_schema or {}, label=body.label
        )
        return EntityTypeOut(
            code=body.code,
            label=body.label,
            color=body.color,
            icon=body.icon,
            sort_order=body.sort_order,
            property_schema=body.property_schema or {},
            entity_count=0,
            created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
        )

    async def list_entity_types(self) -> list[EntityTypeOut]:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?code ?label ?color ?icon ?sortOrder ?propertySchema ?createdAt ?updatedAt
WHERE {{
  ?class a owl:Class ;
         bxmeta:code ?code ;
         rdfs:label ?label .
  FILTER NOT EXISTS {{ ?class a bxmeta:Axiom }}
  OPTIONAL {{ ?class bxmeta:color ?color }}
  OPTIONAL {{ ?class bxmeta:icon ?icon }}
  OPTIONAL {{ ?class bxmeta:sortOrder ?sortOrder }}
  OPTIONAL {{ ?class bxmeta:propertySchema ?propertySchema }}
  OPTIONAL {{ ?class bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?class bxmeta:updatedAt ?updatedAt }}
}}
ORDER BY ?sortOrder ?code
"""
        )
        return [self._row_to_entity_type(r) for r in rows]

    async def get_entity_type(self, code: str) -> EntityTypeOut | None:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?label ?color ?icon ?sortOrder ?propertySchema ?createdAt ?updatedAt
WHERE {{
  ?class a owl:Class ;
         bxmeta:code {_sparql_str(code)} ;
         rdfs:label ?label .
  OPTIONAL {{ ?class bxmeta:color ?color }}
  OPTIONAL {{ ?class bxmeta:icon ?icon }}
  OPTIONAL {{ ?class bxmeta:sortOrder ?sortOrder }}
  OPTIONAL {{ ?class bxmeta:propertySchema ?propertySchema }}
  OPTIONAL {{ ?class bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?class bxmeta:updatedAt ?updatedAt }}
}}
LIMIT 1
"""
        )
        if not rows:
            return None
        item = self._row_to_entity_type({**rows[0], "code": code})
        return item

    async def update_entity_type(self, code: str, body: EntityTypeUpdate) -> EntityTypeOut | None:
        existing = await self.get_entity_type(code)
        if not existing:
            return None
        uri = type_uri(code)
        now = _now_iso()

        # 删除可变属性后重建（GraphDB 不支持 PATCH 单 triple）
        delete_props = [
            "rdfs:label",
            "bxmeta:color",
            "bxmeta:icon",
            "bxmeta:sortOrder",
            "bxmeta:propertySchema",
            "bxmeta:updatedAt",
        ]
        delete_clause = " ;\n    ".join(f"<{uri}> ?p ?o" for _ in delete_props)
        # 用一条 DELETE WHERE 删所有可变谓词
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{
  <{uri}> rdfs:label ?l .
  <{uri}> bxmeta:color ?c .
  <{uri}> bxmeta:icon ?i .
  <{uri}> bxmeta:sortOrder ?so .
  <{uri}> bxmeta:propertySchema ?ps .
  <{uri}> bxmeta:updatedAt ?ua .
}}
WHERE {{
  OPTIONAL {{ <{uri}> rdfs:label ?l }}
  OPTIONAL {{ <{uri}> bxmeta:color ?c }}
  OPTIONAL {{ <{uri}> bxmeta:icon ?i }}
  OPTIONAL {{ <{uri}> bxmeta:sortOrder ?so }}
  OPTIONAL {{ <{uri}> bxmeta:propertySchema ?ps }}
  OPTIONAL {{ <{uri}> bxmeta:updatedAt ?ua }}
}}
"""
        )

        label = body.label if body.label is not None else existing.label
        color = body.color if body.color is not None else existing.color
        icon = body.icon if body.icon is not None else existing.icon
        sort_order = body.sort_order if body.sort_order is not None else existing.sort_order
        prop_schema = (
            body.property_schema
            if body.property_schema is not None
            else existing.property_schema
        )
        schema_json = serialize_property_schema(prop_schema or {})

        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> rdfs:label {_sparql_str(label)} ;
    bxmeta:color {_sparql_str(color)} ;
    bxmeta:icon {_sparql_str(icon)} ;
    bxmeta:sortOrder "{sort_order}"^^xsd:integer ;
    bxmeta:propertySchema {_sparql_str(schema_json)} ;
    bxmeta:updatedAt {_sparql_str(now)} .
}}
"""
        )
        await self.sync_owl_shacl_for_class(code, prop_schema or {}, label=label)
        return await self.get_entity_type(code)

    async def delete_entity_type(self, code: str) -> bool:
        if not await self._entity_type_exists(code):
            return False
        await self.clear_owl_shacl_for_class(code)
        uri = type_uri(code)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{ <{uri}> ?p ?o }}
WHERE {{ <{uri}> ?p ?o }}
"""
        )
        return True

    async def _entity_type_exists(self, code: str) -> bool:
        return await self._db.ask(
            f"""
{_PREFIXES}
ASK {{
  ?class a owl:Class ;
         bxmeta:code {_sparql_str(code)} .
}}
"""
        )

    def _row_to_entity_type(self, row: dict[str, Any]) -> EntityTypeOut:
        created = row.get("createdAt")
        updated = row.get("updatedAt")
        return EntityTypeOut(
            code=str(row.get("code") or ""),
            label=str(row.get("label") or ""),
            color=str(row.get("color") or "blue"),
            icon=str(row.get("icon") or "help-circle"),
            sort_order=_parse_int(row.get("sortOrder"), 100),
            property_schema=deserialize_property_schema(row.get("propertySchema")),
            entity_count=0,
            created_at=_parse_dt(created),
            updated_at=_parse_dt(updated),
        )

    # ── 关系类型 ──────────────────────────────────────────────────────────

    async def create_relation_type(self, body: RelationTypeIn) -> RelationTypeOut:
        if await self._relation_type_exists(body.code):
            raise ValueError(f"关系类型 '{body.code}' 已存在")
        if body.inverse_of:
            inv = await self.get_relation_type(body.inverse_of)
            if not inv:
                raise ValueError(f"互逆关系类型 '{body.inverse_of}' 不存在")

        uri = type_uri(body.code)
        now = _now_iso()
        triples = [
            f"<{uri}> a owl:ObjectProperty",
            f"bxmeta:code {_sparql_str(body.code)}",
            f"rdfs:label {_sparql_str(body.label)}",
            f'bxmeta:transitive "{str(body.transitive).lower()}"^^xsd:boolean',
            f'bxmeta:symmetric "{str(body.symmetric).lower()}"^^xsd:boolean',
            f'bxmeta:sortOrder "{body.sort_order}"^^xsd:integer',
            f"bxmeta:createdAt {_sparql_str(now)}",
            f"bxmeta:updatedAt {_sparql_str(now)}",
        ]
        if body.inverse_of:
            triples.append(f"owl:inverseOf <{type_uri(body.inverse_of)}>")
        insert_body = " ;\n    ".join(triples) + " ."
        domain_range = self._domain_range_insert(uri, body.domain_types, body.range_types)
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  {insert_body}
  {domain_range}
}}
"""
        )
        await self.sync_relation_shape_constraints(
            body.code, body.domain_types or [], body.range_types or []
        )
        return RelationTypeOut(
            code=body.code,
            label=body.label,
            domain_types=body.domain_types or [],
            range_types=body.range_types or [],
            transitive=body.transitive,
            inverse_of=body.inverse_of,
            symmetric=body.symmetric,
            sort_order=body.sort_order,
            relation_count=0,
            created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
        )

    async def list_relation_types(self) -> list[RelationTypeOut]:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?code ?label ?transitive ?symmetric ?sortOrder ?inverseOf ?createdAt ?updatedAt
WHERE {{
  ?prop a owl:ObjectProperty ;
        bxmeta:code ?code ;
        rdfs:label ?label .
  OPTIONAL {{ ?prop bxmeta:transitive ?transitive }}
  OPTIONAL {{ ?prop bxmeta:symmetric ?symmetric }}
  OPTIONAL {{ ?prop bxmeta:sortOrder ?sortOrder }}
  OPTIONAL {{ ?prop owl:inverseOf ?inverseOf }}
  OPTIONAL {{ ?prop bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?prop bxmeta:updatedAt ?updatedAt }}
}}
ORDER BY ?sortOrder ?code
"""
        )
        # 一次查出全部 domain/range，避免按关系类型 N+1 SPARQL
        domain_map: dict[str, list[str]] = {}
        range_map: dict[str, list[str]] = {}
        try:
            dr_rows = await self._db.query(
                f"""
{_PREFIXES}
SELECT ?code ?kind ?typeCode
WHERE {{
  ?prop a owl:ObjectProperty ;
        bxmeta:code ?code .
  {{
    ?prop rdfs:domain ?class .
    BIND("domain" AS ?kind)
  }} UNION {{
    ?prop rdfs:range ?class .
    BIND("range" AS ?kind)
  }}
  ?class bxmeta:code ?typeCode .
}}
"""
            )
            for r in dr_rows:
                code = str(r.get("code") or "")
                kind = str(r.get("kind") or "")
                tc = str(r.get("typeCode") or "")
                if not code or not tc:
                    continue
                target = domain_map if kind == "domain" else range_map
                bucket = target.setdefault(code, [])
                if tc not in bucket:
                    bucket.append(tc)
        except Exception:
            # 降级：无 domain/range 仍返回关系类型列表
            pass

        from app.ontology.constants import code_from_uri

        items: list[RelationTypeOut] = []
        for row in rows:
            code = str(row.get("code") or "")
            inv_uri = row.get("inverseOf")
            inv_code = code_from_uri(str(inv_uri)) if inv_uri else None
            if inv_code and ("/" in inv_code or "#" in inv_code):
                inv_code = None
            items.append(
                RelationTypeOut(
                    code=code,
                    label=str(row.get("label") or ""),
                    domain_types=domain_map.get(code, []),
                    range_types=range_map.get(code, []),
                    transitive=_parse_bool(row.get("transitive")),
                    inverse_of=inv_code,
                    symmetric=_parse_bool(row.get("symmetric")),
                    sort_order=_parse_int(row.get("sortOrder"), 100),
                    relation_count=0,
                    created_at=_parse_dt(row.get("createdAt")),
                    updated_at=_parse_dt(row.get("updatedAt")),
                )
            )
        return items

    async def get_relation_type(self, code: str) -> RelationTypeOut | None:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?label ?transitive ?symmetric ?sortOrder ?inverseOf ?createdAt ?updatedAt
WHERE {{
  ?prop a owl:ObjectProperty ;
        bxmeta:code {_sparql_str(code)} ;
        rdfs:label ?label .
  OPTIONAL {{ ?prop bxmeta:transitive ?transitive }}
  OPTIONAL {{ ?prop bxmeta:symmetric ?symmetric }}
  OPTIONAL {{ ?prop bxmeta:sortOrder ?sortOrder }}
  OPTIONAL {{ ?prop owl:inverseOf ?inverseOf }}
  OPTIONAL {{ ?prop bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?prop bxmeta:updatedAt ?updatedAt }}
}}
LIMIT 1
"""
        )
        if not rows:
            return None
        row = rows[0]
        inv_uri = row.get("inverseOf")
        inv_code = await self._code_for_uri(str(inv_uri)) if inv_uri else None
        return RelationTypeOut(
            code=code,
            label=str(row.get("label") or ""),
            domain_types=await self._fetch_domain_range(code, "domain"),
            range_types=await self._fetch_domain_range(code, "range"),
            transitive=_parse_bool(row.get("transitive")),
            inverse_of=inv_code,
            symmetric=_parse_bool(row.get("symmetric")),
            sort_order=_parse_int(row.get("sortOrder"), 100),
            relation_count=0,
            created_at=_parse_dt(row.get("createdAt")),
            updated_at=_parse_dt(row.get("updatedAt")),
        )

    async def update_relation_type(self, code: str, body: RelationTypeUpdate) -> RelationTypeOut | None:
        existing = await self.get_relation_type(code)
        if not existing:
            return None
        uri = type_uri(code)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{
  <{uri}> rdfs:label ?l .
  <{uri}> rdfs:domain ?d .
  <{uri}> rdfs:range ?r .
  <{uri}> bxmeta:transitive ?t .
  <{uri}> bxmeta:symmetric ?s .
  <{uri}> bxmeta:sortOrder ?so .
  <{uri}> owl:inverseOf ?inv .
  <{uri}> bxmeta:updatedAt ?ua .
}}
WHERE {{
  OPTIONAL {{ <{uri}> rdfs:label ?l }}
  OPTIONAL {{ <{uri}> rdfs:domain ?d }}
  OPTIONAL {{ <{uri}> rdfs:range ?r }}
  OPTIONAL {{ <{uri}> bxmeta:transitive ?t }}
  OPTIONAL {{ <{uri}> bxmeta:symmetric ?s }}
  OPTIONAL {{ <{uri}> bxmeta:sortOrder ?so }}
  OPTIONAL {{ <{uri}> owl:inverseOf ?inv }}
  OPTIONAL {{ <{uri}> bxmeta:updatedAt ?ua }}
}}
"""
        )
        label = body.label if body.label is not None else existing.label
        domain_types = body.domain_types if body.domain_types is not None else existing.domain_types
        range_types = body.range_types if body.range_types is not None else existing.range_types
        transitive = body.transitive if body.transitive is not None else existing.transitive
        symmetric = body.symmetric if body.symmetric is not None else existing.symmetric
        sort_order = body.sort_order if body.sort_order is not None else existing.sort_order
        inverse_of = body.inverse_of if body.inverse_of is not None else existing.inverse_of
        now = _now_iso()

        triples = [
            f"<{uri}> rdfs:label {_sparql_str(label)}",
            f'bxmeta:transitive "{str(transitive).lower()}"^^xsd:boolean',
            f'bxmeta:symmetric "{str(symmetric).lower()}"^^xsd:boolean',
            f'bxmeta:sortOrder "{sort_order}"^^xsd:integer',
            f"bxmeta:updatedAt {_sparql_str(now)}",
        ]
        if inverse_of:
            triples.append(f"owl:inverseOf <{type_uri(inverse_of)}>")
        insert_main = " ;\n    ".join(triples) + " ."
        domain_range = self._domain_range_insert(uri, domain_types, range_types)
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  {insert_main}
  {domain_range}
}}
"""
        )
        return await self.get_relation_type(code)

    async def delete_relation_type(self, code: str) -> bool:
        if not await self._relation_type_exists(code):
            return False
        uri = type_uri(code)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{ <{uri}> ?p ?o }}
WHERE {{ <{uri}> ?p ?o }}
"""
        )
        return True

    async def _relation_type_exists(self, code: str) -> bool:
        return await self._db.ask(
            f"""
{_PREFIXES}
ASK {{
  ?prop a owl:ObjectProperty ;
        bxmeta:code {_sparql_str(code)} .
}}
"""
        )

    async def _fetch_domain_range(self, code: str, kind: str) -> list[str]:
        pred = "rdfs:domain" if kind == "domain" else "rdfs:range"
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?typeCode
WHERE {{
  <{type_uri(code)}> {pred} ?class .
  ?class bxmeta:code ?typeCode .
}}
"""
        )
        return [str(r.get("typeCode") or "") for r in rows if r.get("typeCode")]

    async def _code_for_uri(self, uri: str) -> str | None:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?code WHERE {{ <{uri}> bxmeta:code ?code . }} LIMIT 1
"""
        )
        if rows and rows[0].get("code"):
            return str(rows[0]["code"])
        return None

    @staticmethod
    def _domain_range_insert(uri: str, domains: list[str], ranges: list[str]) -> str:
        lines: list[str] = []
        for d in domains or []:
            lines.append(f"<{uri}> rdfs:domain <{type_uri(d)}> .")
        for r in ranges or []:
            lines.append(f"<{uri}> rdfs:range <{type_uri(r)}> .")
        return "\n  ".join(lines)

    # ── 公理（Cypher 写图规则，元数据存 GraphDB，执行仍走 Neo4j）──────────

    async def create_axiom(self, body: AxiomIn) -> AxiomOut:
        uri = axiom_uri(body.name)
        if await self._axiom_exists(body.name):
            raise ValueError(f"公理 '{body.name}' 已存在")
        now = _now_iso()
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> a bxmeta:Axiom ;
    bxmeta:name {_sparql_str(body.name)} ;
    bxmeta:description {_sparql_str(body.description)} ;
    bxmeta:cypherRule {_sparql_str(body.cypher_rule)} ;
    bxmeta:active "{str(body.active).lower()}"^^xsd:boolean ;
    bxmeta:createdAt {_sparql_str(now)} ;
    bxmeta:updatedAt {_sparql_str(now)} .
}}
"""
        )
        return AxiomOut(
            name=body.name,
            description=body.description,
            cypher_rule=body.cypher_rule,
            active=body.active,
            created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
        )

    async def list_axioms(self) -> list[AxiomOut]:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?name ?description ?cypherRule ?active ?lastRunAt ?lastRunResult ?createdAt ?updatedAt
WHERE {{
  ?a a bxmeta:Axiom ;
     bxmeta:name ?name .
  OPTIONAL {{ ?a bxmeta:description ?description }}
  OPTIONAL {{ ?a bxmeta:cypherRule ?cypherRule }}
  OPTIONAL {{ ?a bxmeta:active ?active }}
  OPTIONAL {{ ?a bxmeta:lastRunAt ?lastRunAt }}
  OPTIONAL {{ ?a bxmeta:lastRunResult ?lastRunResult }}
  OPTIONAL {{ ?a bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?a bxmeta:updatedAt ?updatedAt }}
}}
ORDER BY ?name
"""
        )
        return [self._row_to_axiom(r) for r in rows]

    async def get_axiom(self, name: str) -> AxiomOut | None:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?description ?cypherRule ?active ?lastRunAt ?lastRunResult ?createdAt ?updatedAt
WHERE {{
  ?a a bxmeta:Axiom ;
     bxmeta:name {_sparql_str(name)} .
  OPTIONAL {{ ?a bxmeta:description ?description }}
  OPTIONAL {{ ?a bxmeta:cypherRule ?cypherRule }}
  OPTIONAL {{ ?a bxmeta:active ?active }}
  OPTIONAL {{ ?a bxmeta:lastRunAt ?lastRunAt }}
  OPTIONAL {{ ?a bxmeta:lastRunResult ?lastRunResult }}
  OPTIONAL {{ ?a bxmeta:createdAt ?createdAt }}
  OPTIONAL {{ ?a bxmeta:updatedAt ?updatedAt }}
}}
LIMIT 1
"""
        )
        if not rows:
            return None
        return self._row_to_axiom({**rows[0], "name": name})

    async def update_axiom(self, name: str, body: AxiomUpdate) -> AxiomOut | None:
        existing = await self.get_axiom(name)
        if not existing:
            return None
        uri = axiom_uri(name)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{
  <{uri}> bxmeta:description ?d .
  <{uri}> bxmeta:cypherRule ?c .
  <{uri}> bxmeta:active ?a .
  <{uri}> bxmeta:updatedAt ?u .
}}
WHERE {{
  OPTIONAL {{ <{uri}> bxmeta:description ?d }}
  OPTIONAL {{ <{uri}> bxmeta:cypherRule ?c }}
  OPTIONAL {{ <{uri}> bxmeta:active ?a }}
  OPTIONAL {{ <{uri}> bxmeta:updatedAt ?u }}
}}
"""
        )
        desc = body.description if body.description is not None else existing.description
        cypher = body.cypher_rule if body.cypher_rule is not None else existing.cypher_rule
        active = body.active if body.active is not None else existing.active
        now = _now_iso()
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> bxmeta:description {_sparql_str(desc)} ;
    bxmeta:cypherRule {_sparql_str(cypher)} ;
    bxmeta:active "{str(active).lower()}"^^xsd:boolean ;
    bxmeta:updatedAt {_sparql_str(now)} .
}}
"""
        )
        return await self.get_axiom(name)

    async def delete_axiom(self, name: str) -> bool:
        if not await self._axiom_exists(name):
            return False
        uri = axiom_uri(name)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{ <{uri}> ?p ?o }}
WHERE {{ <{uri}> ?p ?o }}
"""
        )
        return True

    async def update_axiom_run_result(
        self, name: str, *, success: bool, affected: int | None, error: str | None
    ) -> None:
        uri = axiom_uri(name)
        now = _now_iso()
        result_text = f"OK, affected={affected}" if success else f"ERROR: {(error or '')[:500]}"
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{ <{uri}> bxmeta:lastRunAt ?a . <{uri}> bxmeta:lastRunResult ?r . }}
WHERE {{
  OPTIONAL {{ <{uri}> bxmeta:lastRunAt ?a }}
  OPTIONAL {{ <{uri}> bxmeta:lastRunResult ?r }}
}}
INSERT DATA {{
  <{uri}> bxmeta:lastRunAt {_sparql_str(now)} ;
    bxmeta:lastRunResult {_sparql_str(result_text)} .
}}
"""
        )

    async def list_subclass_edges(self) -> list[dict[str, str]]:
        """列出 rdfs:subClassOf 边（child_code → parent_code）。"""
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?child ?parent WHERE {{
  ?c a owl:Class ; bxmeta:code ?child ; rdfs:subClassOf ?p .
  ?p bxmeta:code ?parent .
  FILTER(?child != ?parent)
}}
"""
        )
        return [
            {"child": str(r.get("child") or ""), "parent": str(r.get("parent") or "")}
            for r in rows
            if r.get("child") and r.get("parent")
        ]

    async def set_subclass_of(self, child_code: str, parent_code: str) -> None:
        """写入 rdfs:subClassOf（child ⊑ parent）。"""
        if not child_code or not parent_code or child_code == parent_code:
            return
        child = type_uri(child_code)
        parent = type_uri(parent_code)
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{child}> rdfs:subClassOf <{parent}> .
}}
"""
        )

    # ── OWL / SHACL / SKOS 扩展 ───────────────────────────────────────────

    async def clear_owl_shacl_for_class(self, class_code: str) -> None:
        """清除类相关的 DatatypeProperty、NodeShape 及旧属性约束。"""
        class_u = type_uri(class_code)
        shape_u = shape_uri(class_code)
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{
  ?prop ?pp ?po .
}}
WHERE {{
  ?prop a owl:DatatypeProperty ; rdfs:domain <{class_u}> .
  ?prop ?pp ?po .
}}
"""
        )
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{
  <{shape_u}> ?p ?o .
  ?bn ?bp ?bo .
}}
WHERE {{
  OPTIONAL {{ <{shape_u}> ?p ?o }}
  OPTIONAL {{
    <{shape_u}> sh:property ?bn .
    ?bn ?bp ?bo .
  }}
}}
"""
        )

    async def sync_owl_shacl_for_class(
        self,
        class_code: str,
        property_schema: dict[str, Any],
        *,
        label: str | None = None,
    ) -> None:
        """按 property_schema 重建 DatatypeProperty + SHACL NodeShape。"""
        await self.clear_owl_shacl_for_class(class_code)
        props_insert = build_datatype_properties_insert(class_code, property_schema or {})
        shape_insert = build_node_shape_insert(
            class_code, property_schema or {}, label=label
        )
        body = "\n".join(x for x in (props_insert, shape_insert) if x.strip())
        if not body.strip():
            # 无属性时仍写入空 NodeShape，便于校验目标类存在
            body = build_node_shape_insert(class_code, {}, label=label)
        await self._db.update(
            f"""
{SHACL_PREFIXES}
INSERT DATA {{
{body}
}}
"""
        )

    async def sync_relation_shape_constraints(
        self,
        relation_code: str,
        domain_types: list[str],
        range_types: list[str],
    ) -> None:
        frag = build_relation_shape_fragment(relation_code, domain_types, range_types)
        if not frag.strip():
            return
        await self._db.update(
            f"""
{SHACL_PREFIXES}
INSERT DATA {{
{frag}
}}
"""
        )

    async def add_alt_label(self, class_code: str, alt_label: str) -> None:
        if not alt_label or not class_code:
            return
        uri = type_uri(class_code)
        # 避免重复
        exists = await self._db.ask(
            f"""
{_PREFIXES}
ASK {{ <{uri}> skos:altLabel {_sparql_str(alt_label)} . }}
"""
        )
        if exists:
            return
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> skos:altLabel {_sparql_str(alt_label)} .
}}
"""
        )

    async def list_alt_labels(self, class_code: str) -> list[str]:
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?alt WHERE {{
  <{type_uri(class_code)}> skos:altLabel ?alt .
}}
"""
        )
        return [str(r.get("alt") or "") for r in rows if r.get("alt")]

    async def set_equivalent_class(self, source_code: str, target_code: str) -> None:
        if not source_code or not target_code or source_code == target_code:
            return
        src = type_uri(source_code)
        tgt = type_uri(target_code)
        await self._db.update(
            f"""
{_PREFIXES}
INSERT DATA {{
  <{src}> owl:equivalentClass <{tgt}> .
  <{tgt}> owl:equivalentClass <{src}> .
}}
"""
        )
        # 标记 source 为已合并（软弃用）
        await self._db.update(
            f"""
{_PREFIXES}
DELETE {{ <{src}> bxmeta:deprecated ?d . <{src}> bxmeta:mergedInto ?m . }}
WHERE {{
  OPTIONAL {{ <{src}> bxmeta:deprecated ?d }}
  OPTIONAL {{ <{src}> bxmeta:mergedInto ?m }}
}}
INSERT DATA {{
  <{src}> bxmeta:deprecated "true"^^xsd:boolean ;
    bxmeta:mergedInto {_sparql_str(target_code)} .
}}
"""
        )

    async def resolve_canonical_code(self, code: str) -> str:
        """若类已合并，返回 canonical code。"""
        rows = await self._db.query(
            f"""
{_PREFIXES}
SELECT ?into WHERE {{
  <{type_uri(code)}> bxmeta:mergedInto ?into .
}}
LIMIT 1
"""
        )
        if rows and rows[0].get("into"):
            return str(rows[0]["into"])
        return code

    async def fetch_shape_and_ontology_turtle(self, class_code: str | None = None) -> str:
        """导出 shapes + 相关类/属性的精简 Turtle（供 pySHACL）。"""
        from app.ontology.owl_export import build_shapes_graph_turtle

        return await build_shapes_graph_turtle(self._db, class_code=class_code)

    async def _axiom_exists(self, name: str) -> bool:
        return await self._db.ask(
            f"""
{_PREFIXES}
ASK {{ ?a a bxmeta:Axiom ; bxmeta:name {_sparql_str(name)} . }}
"""
        )

    def _row_to_axiom(self, row: dict[str, Any]) -> AxiomOut:
        return AxiomOut(
            name=str(row.get("name") or ""),
            description=str(row.get("description") or ""),
            cypher_rule=str(row.get("cypherRule") or ""),
            active=_parse_bool(row.get("active")),
            last_run_at=_parse_dt(row.get("lastRunAt")),
            last_run_result=row.get("lastRunResult"),
            created_at=_parse_dt(row.get("createdAt")),
            updated_at=_parse_dt(row.get("updatedAt")),
        )


def _parse_dt(val: Any) -> datetime | None:
    if not val:
        return None
    try:
        s = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
