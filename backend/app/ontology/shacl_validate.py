"""将 Neo4j 实体投影为 RDF，并用 pySHACL 对 SHACL shapes 做校验。"""

from __future__ import annotations

import logging
from typing import Any

from app.ontology.constants import datatype_prop_uri, type_uri
from app.ontology.shacl_shapes import xsd_for_prop_type

logger = logging.getLogger(__name__)


def project_entity_to_turtle(
    *,
    type_code: str,
    name: str,
    properties: dict[str, Any] | None = None,
    entity_id: str = "urn:benxi:entity:candidate",
) -> str:
    """候选实例 → Turtle（仅用于校验，不落库）。"""
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import RDF

    g = Graph()
    subj = URIRef(entity_id if str(entity_id).startswith(("http", "urn:")) else f"urn:benxi:entity:{entity_id}")
    class_u = URIRef(type_uri(type_code))
    g.add((subj, RDF.type, class_u))
    props = dict(properties or {})
    # 若 schema 未单独声明 name，不写入，避免假阳性
    _ = name
    for key, val in props.items():
        if val is None:
            continue
        prop_u = URIRef(datatype_prop_uri(type_code, key))
        lit = _to_literal(val)
        g.add((subj, prop_u, lit))
    return g.serialize(format="turtle")


def _to_literal(val: Any):
    from rdflib import Literal
    from rdflib.namespace import XSD

    if isinstance(val, bool):
        return Literal(val, datatype=XSD.boolean)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return Literal(val, datatype=XSD.decimal)
    return Literal(str(val))


def validate_entity_with_shacl(
    *,
    shapes_turtle: str,
    type_code: str,
    name: str,
    properties: dict[str, Any] | None = None,
    property_schema: dict[str, Any] | None = None,
) -> list[str]:
    """用 pySHACL 校验；失败时回退到 property_schema 本地规则。"""
    errors: list[str] = []
    try:
        from pyshacl import validate as shacl_validate

        data_ttl = project_entity_to_turtle(
            type_code=type_code, name=name or "", properties=properties or {}
        )
        conforms, _results_graph, results_text = shacl_validate(
            data_graph=data_ttl,
            data_graph_format="turtle",
            shacl_graph=shapes_turtle,
            shacl_graph_format="turtle",
            inference="rdfs",
            abort_on_first=False,
            meta_shacl=False,
            advanced=True,
            js=False,
            debug=False,
        )
        if not conforms:
            # 提取可读行
            for line in str(results_text or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Constraint Violation") or "sh:" in line or "MinCount" in line:
                    errors.append(line[:300])
            if not errors:
                errors.append(str(results_text)[:500] or "SHACL 校验未通过")
            return errors
        return []
    except Exception as exc:
        logger.warning("pySHACL 不可用或失败，回退 JSON schema: %s", exc)
        return _fallback_property_schema_errors(property_schema or {}, properties or {})


def _fallback_property_schema_errors(
    property_schema: dict[str, Any],
    properties: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    for key, pdef in (property_schema or {}).items():
        if hasattr(pdef, "model_dump"):
            pdef = pdef.model_dump()
        if not isinstance(pdef, dict):
            continue
        if pdef.get("required") and key not in properties:
            errors.append(f"缺少必需属性: {key}")
        value = properties.get(key)
        if value is not None and pdef.get("type") == "number":
            try:
                float(value)
            except (ValueError, TypeError):
                errors.append(f"属性 '{key}' 需要数值类型")
        # 轻量类型提示
        expected = pdef.get("type")
        if value is not None and expected in ("string", "text", "url") and not isinstance(value, str):
            errors.append(f"属性 '{key}' 需要字符串类型 ({xsd_for_prop_type(str(expected))})")
    return errors
