"""将 Neo4j 中遗留的 Ontology* 节点一次性迁移到 GraphDB。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.core.neo4j_converter import deserialize_property_schema, serialize_property_schema
from app.core.graphdb import GraphDbClient
from app.ontology.constants import axiom_uri, type_uri
from app.ontology.rdf_store import _PREFIXES, _sparql_str

logger = logging.getLogger(__name__)


async def migrate_neo4j_tbox_if_needed(client: GraphDbClient) -> None:
    """GraphDB 为空且 Neo4j 仍有 TBox 节点时执行迁移并清理 Neo4j。"""
    from app.core.neo4j import get_neo4j

    entity_types = await client.query(
        f"""
{_PREFIXES}
SELECT (COUNT(?c) AS ?cnt) WHERE {{ ?c a owl:Class ; bxmeta:code ?code . }}
"""
    )
    existing = 0
    if entity_types:
        try:
            existing = int(entity_types[0].get("cnt") or 0)
        except (TypeError, ValueError):
            existing = 0
    if existing > 0:
        return

    try:
        driver = await get_neo4j()
    except Exception:
        return

    async with driver.session() as session:
        et_result = await session.run(
            "MATCH (et:OntologyEntityType) RETURN et ORDER BY et.sort_order, et.code"
        )
        entity_rows = [dict(r["et"]) async for r in et_result]
        if not entity_rows:
            return

        rt_result = await session.run(
            "MATCH (rt:OntologyRelationType) RETURN rt ORDER BY rt.sort_order, rt.code"
        )
        relation_rows = [dict(r["rt"]) async for r in rt_result]

        ax_result = await session.run("MATCH (a:OntologyAxiom) RETURN a ORDER BY a.name")
        axiom_rows = [dict(r["a"]) async for r in ax_result]

    logger.info(
        "Migrating TBox from Neo4j to GraphDB: %d entity types, %d relation types, %d axioms",
        len(entity_rows),
        len(relation_rows),
        len(axiom_rows),
    )

    for et in entity_rows:
        await _import_entity_type(client, et)
    for rt in relation_rows:
        await _import_relation_type(client, rt)
    for rt in relation_rows:
        inv = rt.get("inverse_of") or ""
        if inv:
            await _set_inverse(client, rt.get("code", ""), inv)
    for ax in axiom_rows:
        await _import_axiom(client, ax)

    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n:OntologyEntityType OR n:OntologyRelationType OR n:OntologyAxiom
            DETACH DELETE n
            """
        )
    logger.info("Neo4j TBox nodes removed after GraphDB migration")


async def _import_entity_type(client: GraphDbClient, props: dict[str, Any]) -> None:
    code = props.get("code", "")
    if not code:
        return
    schema = props.get("property_schema") or {}
    if isinstance(schema, str):
        schema = deserialize_property_schema(schema)
    else:
        schema = deserialize_property_schema(schema)
    schema_json = serialize_property_schema(schema)
    uri = type_uri(code)
    created = _dt(props.get("created_at"))
    updated = _dt(props.get("updated_at"))
    await client.update(
        f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> a owl:Class ;
    bxmeta:code {_sparql_str(code)} ;
    rdfs:label {_sparql_str(props.get("label") or code)} ;
    bxmeta:color {_sparql_str(props.get("color") or "blue")} ;
    bxmeta:icon {_sparql_str(props.get("icon") or "help-circle")} ;
    bxmeta:sortOrder "{int(props.get('sort_order') or 100)}"^^xsd:integer ;
    bxmeta:propertySchema {_sparql_str(schema_json)} ;
    bxmeta:createdAt {_sparql_str(created)} ;
    bxmeta:updatedAt {_sparql_str(updated)} .
}}
"""
    )


async def _import_relation_type(client: GraphDbClient, props: dict[str, Any]) -> None:
    code = props.get("code", "")
    if not code:
        return
    uri = type_uri(code)
    domains = props.get("domain_types") or []
    ranges = props.get("range_types") or []
    domain_lines = "\n  ".join(f"<{uri}> rdfs:domain <{type_uri(d)}> ." for d in domains)
    range_lines = "\n  ".join(f"<{uri}> rdfs:range <{type_uri(r)}> ." for r in ranges)
    created = _dt(props.get("created_at"))
    updated = _dt(props.get("updated_at"))
    await client.update(
        f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> a owl:ObjectProperty ;
    bxmeta:code {_sparql_str(code)} ;
    rdfs:label {_sparql_str(props.get("label") or code)} ;
    bxmeta:transitive "{str(bool(props.get('transitive'))).lower()}"^^xsd:boolean ;
    bxmeta:symmetric "{str(bool(props.get('symmetric'))).lower()}"^^xsd:boolean ;
    bxmeta:sortOrder "{int(props.get('sort_order') or 100)}"^^xsd:integer ;
    bxmeta:createdAt {_sparql_str(created)} ;
    bxmeta:updatedAt {_sparql_str(updated)} .
  {domain_lines}
  {range_lines}
}}
"""
    )


async def _set_inverse(client: GraphDbClient, code: str, inverse_code: str) -> None:
    if not code or not inverse_code:
        return
    await client.update(
        f"""
{_PREFIXES}
INSERT DATA {{
  <{type_uri(code)}> owl:inverseOf <{type_uri(inverse_code)}> .
}}
"""
    )


async def _import_axiom(client: GraphDbClient, props: dict[str, Any]) -> None:
    name = props.get("name", "")
    if not name:
        return
    uri = axiom_uri(name)
    created = _dt(props.get("created_at"))
    updated = _dt(props.get("updated_at"))
    last_run = _dt(props.get("last_run_at")) if props.get("last_run_at") else None
    extra = ""
    if last_run:
        extra += f"bxmeta:lastRunAt {_sparql_str(last_run)} ;\n    "
    if props.get("last_run_result"):
        extra += f"bxmeta:lastRunResult {_sparql_str(str(props.get('last_run_result')))} ;\n    "
    await client.update(
        f"""
{_PREFIXES}
INSERT DATA {{
  <{uri}> a bxmeta:Axiom ;
    bxmeta:name {_sparql_str(name)} ;
    bxmeta:description {_sparql_str(props.get("description") or "")} ;
    bxmeta:cypherRule {_sparql_str(props.get("cypher_rule") or "")} ;
    bxmeta:active "{str(bool(props.get('active', True))).lower()}"^^xsd:boolean ;
    {extra}
    bxmeta:createdAt {_sparql_str(created)} ;
    bxmeta:updatedAt {_sparql_str(updated)} .
}}
"""
    )


def _dt(val: Any) -> str:
    if val is None:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if hasattr(val, "isoformat"):
        return val.isoformat().replace("+00:00", "Z")
    return str(val)
