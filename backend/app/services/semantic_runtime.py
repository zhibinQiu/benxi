"""平台语义运行时工厂 — 组装 ``app.semantic`` 与 Neo4j / 本体持久化。"""

from __future__ import annotations

from app.semantic.kg.service import KgQueryService
from app.semantic.ontology.schema_view import SchemaView
from app.semantic.ontology.service import OntologyHubService
from app.services.semantic_field_binding_service import field_mapper_from_db


async def get_kg_query_service() -> KgQueryService:
    """注入 Neo4j driver 与本体 Schema 的 KgQueryService。"""
    from app.core.neo4j import get_neo4j
    from app.services.ontology_factory import get_ontology_service

    driver = await get_neo4j()
    ontology = await get_ontology_service()
    return KgQueryService(driver, schema=SchemaView(ontology))


async def get_ontology_hub_service(
    *,
    kg: KgQueryService | None = None,
) -> OntologyHubService:
    """组装带 Schema / 字段映射工厂 / Kg 的语义中枢。"""
    from app.services.ontology_factory import get_ontology_service

    ontology = await get_ontology_service()
    schema = SchemaView(ontology)
    if kg is None:
        kg = await get_kg_query_service()
    else:
        kg.bind_schema(schema)
    return OntologyHubService(
        schema=schema,
        kg=kg,
        mapper_factory=field_mapper_from_db,
    )
