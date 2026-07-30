"""OWL/SHACL 与同义合并单元测试（不依赖 GraphDB/Neo4j）。"""

from __future__ import annotations

from app.ontology.shacl_shapes import (
    build_datatype_properties_insert,
    build_node_shape_insert,
    xsd_for_prop_type,
)
from app.ontology.shacl_validate import (
    project_entity_to_turtle,
    validate_entity_with_shacl,
)
from app.ontology.synonym_merge import (
    builtin_canonical_for_label,
    normalize_label,
    resolve_concept_against_catalog,
)


def test_xsd_mapping():
    assert "decimal" in xsd_for_prop_type("number")
    assert "boolean" in xsd_for_prop_type("boolean")
    assert "string" in xsd_for_prop_type("string")


def test_build_node_shape_has_min_count_for_required():
    schema = {
        "value": {"type": "number", "required": True, "description": "排放量"},
        "unit": {"type": "string", "required": False, "description": "单位"},
    }
    ttl_frag = build_node_shape_insert("carbon_emission", schema, label="碳排放")
    assert "sh:NodeShape" in ttl_frag
    assert "sh:minCount 1" in ttl_frag
    assert "carbon_emission" in ttl_frag
    props = build_datatype_properties_insert("carbon_emission", schema)
    assert "owl:DatatypeProperty" in props
    assert "decimal" in props


def test_shacl_rejects_missing_required_property():
    schema = {
        "value": {"type": "number", "required": True, "description": "排放量"},
    }
    shape_body = build_node_shape_insert("metric", schema)
    props_body = build_datatype_properties_insert("metric", schema)
    shapes_ttl = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix bx: <http://benxi.ai/ontology/> .
@prefix bxmeta: <http://benxi.ai/ontology/meta#> .
@prefix bxprop: <http://benxi.ai/ontology/prop/> .
@prefix bxshape: <http://benxi.ai/ontology/shapes/> .

bx:metric a owl:Class ; rdfs:label "指标" .

{props_body}
{shape_body}
"""
    # 补全 PREFIX 风格片段为合法 turtle：build_* 返回的是 SPARQL INSERT 风格
    # 改用纯 rdflib 构造的校验路径：空 properties 应失败（fallback 或 shacl）
    errors = validate_entity_with_shacl(
        shapes_turtle=_shapes_turtle_for_metric(),
        type_code="metric",
        name="测试指标",
        properties={},
        property_schema=schema,
    )
    assert errors, "缺必填属性应产生错误"
    assert any("value" in e or "必需" in e or "MinCount" in e or "minCount" in e.lower() for e in errors)


def _shapes_turtle_for_metric() -> str:
    return """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix bx: <http://benxi.ai/ontology/> .

bx:metric a owl:Class ; rdfs:label "指标" .
<http://benxi.ai/ontology/prop/metric/value> a owl:DatatypeProperty ;
  rdfs:domain bx:metric ;
  rdfs:range xsd:decimal .
<http://benxi.ai/ontology/shapes/metricShape> a sh:NodeShape ;
  sh:targetClass bx:metric ;
  sh:property [
    sh:path <http://benxi.ai/ontology/prop/metric/value> ;
    sh:datatype xsd:decimal ;
    sh:minCount 1 ;
    sh:name "value"
  ] .
"""


def test_shacl_passes_when_required_present():
    errors = validate_entity_with_shacl(
        shapes_turtle=_shapes_turtle_for_metric(),
        type_code="metric",
        name="测试指标",
        properties={"value": 12.5},
        property_schema={"value": {"type": "number", "required": True}},
    )
    assert errors == []


def test_project_entity_turtle_contains_type():
    ttl = project_entity_to_turtle(
        type_code="metric",
        name="x",
        properties={"value": 1},
    )
    assert "metric" in ttl
    assert "value" in ttl


def test_builtin_synonym_carbon_emission():
    assert builtin_canonical_for_label("碳排放量") == "carbon_emission"
    assert builtin_canonical_for_label("CO2排放") == "carbon_emission"
    assert builtin_canonical_for_label("二氧化碳排放") == "carbon_emission"


def test_resolve_concept_merges_by_synonym():
    existing = [
        {"code": "carbon_emission", "label": "碳排放", "alt_labels": []},
        {"code": "enterprise", "label": "企业", "alt_labels": ["公司"]},
    ]
    m = resolve_concept_against_catalog(
        code="co2_emission",
        label="二氧化碳排放",
        existing=existing,
    )
    assert m is not None
    assert m.canonical_code == "carbon_emission"


def test_resolve_concept_merges_by_alt_label():
    existing = [
        {"code": "boiler", "label": "锅炉", "alt_labels": ["蒸汽锅炉"]},
    ]
    m = resolve_concept_against_catalog(
        code="steam_boiler",
        label="蒸汽锅炉",
        existing=existing,
    )
    assert m is not None
    assert m.canonical_code == "boiler"
    assert m.matched_by == "alt_label"


def test_normalize_label_strips_company_suffix():
    assert normalize_label("本析科技有限公司") == normalize_label("本析科技")
