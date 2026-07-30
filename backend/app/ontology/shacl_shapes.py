"""由 property_schema / 关系类型生成 OWL DatatypeProperty 与 SHACL NodeShape。"""

from __future__ import annotations

import json
from typing import Any

from app.ontology.constants import (
    BX_NS,
    BXMETA_NS,
    SHACL_NS,
    SKOS_NS,
    datatype_prop_uri,
    shape_uri,
    type_uri,
)

_XSD = {
    "string": "http://www.w3.org/2001/XMLSchema#string",
    "text": "http://www.w3.org/2001/XMLSchema#string",
    "url": "http://www.w3.org/2001/XMLSchema#anyURI",
    "number": "http://www.w3.org/2001/XMLSchema#decimal",
    "date": "http://www.w3.org/2001/XMLSchema#date",
    "boolean": "http://www.w3.org/2001/XMLSchema#boolean",
}


def xsd_for_prop_type(prop_type: str) -> str:
    return _XSD.get(prop_type or "string", _XSD["string"])


def _sparql_str(val: str) -> str:
    return json.dumps(val, ensure_ascii=False)


def build_datatype_properties_insert(
    class_code: str,
    property_schema: dict[str, Any],
) -> str:
    """生成 owl:DatatypeProperty INSERT DATA 片段（不含 PREFIX）。"""
    class_u = type_uri(class_code)
    lines: list[str] = []
    for pname, pdef in (property_schema or {}).items():
        if not pname:
            continue
        if hasattr(pdef, "model_dump"):
            pdef = pdef.model_dump()
        if not isinstance(pdef, dict):
            continue
        ptype = str(pdef.get("type") or "string")
        desc = str(pdef.get("description") or pname)
        prop_u = datatype_prop_uri(class_code, pname)
        xsd = xsd_for_prop_type(ptype)
        lines.append(
            f"""  <{prop_u}> a owl:DatatypeProperty ;
    rdfs:domain <{class_u}> ;
    rdfs:range <{xsd}> ;
    rdfs:label {_sparql_str(pname)} ;
    bxmeta:code {_sparql_str(pname)} ;
    bxmeta:propType {_sparql_str(ptype)} ;
    bxmeta:required "{str(bool(pdef.get('required'))).lower()}"^^xsd:boolean ;
    rdfs:comment {_sparql_str(desc)} ."""
        )
    return "\n".join(lines)


def build_node_shape_insert(
    class_code: str,
    property_schema: dict[str, Any],
    *,
    label: str | None = None,
) -> str:
    """生成 sh:NodeShape INSERT DATA 片段（不含 PREFIX）。"""
    class_u = type_uri(class_code)
    shape_u = shape_uri(class_code)
    shape_label = label or f"{class_code}Shape"
    prop_blocks: list[str] = []
    for pname, pdef in (property_schema or {}).items():
        if not pname:
            continue
        if hasattr(pdef, "model_dump"):
            pdef = pdef.model_dump()
        if not isinstance(pdef, dict):
            continue
        ptype = str(pdef.get("type") or "string")
        prop_u = datatype_prop_uri(class_code, pname)
        xsd = xsd_for_prop_type(ptype)
        required = bool(pdef.get("required"))
        extra = f"\n      sh:minCount 1 ;" if required else ""
        prop_blocks.append(
            f"""    sh:property [
      sh:path <{prop_u}> ;
      sh:datatype <{xsd}> ;{extra}
      sh:name {_sparql_str(pname)}
    ] ;"""
        )
    props_body = "\n".join(prop_blocks) if prop_blocks else ""
    return f"""  <{shape_u}> a sh:NodeShape ;
    sh:targetClass <{class_u}> ;
    rdfs:label {_sparql_str(shape_label)} ;
    bxmeta:forClass {_sparql_str(class_code)} ;
{props_body}
    sh:closed false ."""


def build_relation_shape_fragment(
    relation_code: str,
    domain_types: list[str],
    range_types: list[str],
) -> str:
    """为 ObjectProperty 补充 domain 侧 NodeShape 上的关系约束片段（可选增强）。"""
    if not domain_types or not range_types:
        return ""
    rel_u = type_uri(relation_code)
    # 挂在每个 domain 类的 shape 上
    blocks: list[str] = []
    for dom in domain_types:
        shape_u = shape_uri(dom)
        for rng in range_types:
            rng_u = type_uri(rng)
            blocks.append(
                f"""  <{shape_u}> sh:property [
    sh:path <{rel_u}> ;
    sh:class <{rng_u}> ;
    sh:name {_sparql_str(relation_code)}
  ] ."""
            )
    return "\n".join(blocks)


SHACL_PREFIXES = f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX sh: <{SHACL_NS}>
PREFIX skos: <{SKOS_NS}>
PREFIX bx: <{BX_NS}>
PREFIX bxmeta: <{BXMETA_NS}>
"""
