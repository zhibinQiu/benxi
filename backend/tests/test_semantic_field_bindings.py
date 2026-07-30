"""问数映射自动发现与 FieldMapper 读库。"""

from __future__ import annotations

from app.semantic.models import ResolvedConcept
from app.semantic.ontology.field_mapper import FieldMapper
from app.services.semantic_field_binding_service import (
    discover_bindings,
    load_sql_maps,
)


def test_discover_bindings_finds_person_phone():
    from unittest.mock import MagicMock

    db = MagicMock()
    db.get_bind.side_effect = RuntimeError("no bind")
    rows = discover_bindings(db)
    phones = [r for r in rows if r.concept == "person" and r.property_key == "phone"]
    assert phones
    assert phones[0].table_name == "users"
    assert phones[0].column_name == "phone"
    joins = [r for r in rows if r.join_template == "person_org"]
    assert joins


def test_field_mapper_prefers_sql_over_neo4j_for_phone():
    mapper = FieldMapper(
        sql_bindings={("person", "phone"): ("users", "phone", "auto")},
        sql_join_bindings={},
    )
    concepts = [
        ResolvedConcept(
            type_code="person",
            property_keys=["phone"],
            confidence=0.9,
        )
    ]
    bindings = mapper.map_concepts(concepts)
    sources = {(b.property_key, b.source) for b in bindings}
    assert ("phone", "sql") in sources
    assert ("phone", "neo4j") not in sources


def test_load_sql_maps_fallback_without_db():
    sql, joins = load_sql_maps(None)
    assert ("person", "phone") in sql
    assert ("person", "department") in joins
