"""本体 OWL/SHACL Turtle 导出。"""

from __future__ import annotations

import logging
from typing import Any

from app.ontology.constants import (
    BX_NS,
    BXMETA_NS,
    PROP_NS,
    SHACL_NS,
    SHAPE_NS,
    SKOS_NS,
    shape_uri,
    type_uri,
)
from app.ontology.shacl_shapes import SHACL_PREFIXES, xsd_for_prop_type

logger = logging.getLogger(__name__)


async def build_shapes_graph_turtle(
    graphdb: Any,
    *,
    class_code: str | None = None,
) -> str:
    """从 GraphDB 拉出类/属性/Shape，拼成供 pySHACL 使用的 Turtle。"""
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import OWL, RDF, RDFS, XSD

    g = Graph()
    SH = Namespace(SHACL_NS)
    SKOS = Namespace(SKOS_NS)
    BXMETA = Namespace(BXMETA_NS)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("sh", SH)
    g.bind("skos", SKOS)
    g.bind("bxmeta", BXMETA)
    g.bind("bx", Namespace(BX_NS))
    g.bind("bxprop", Namespace(PROP_NS))
    g.bind("bxshape", Namespace(SHAPE_NS))

    code_filter = ""
    if class_code:
        code_filter = f"FILTER(?code = {_q(class_code)})"

    rows = await graphdb.query(
        f"""
{SHACL_PREFIXES}
SELECT ?code ?label ?propertySchema WHERE {{
  ?class a owl:Class ; bxmeta:code ?code ; rdfs:label ?label .
  FILTER NOT EXISTS {{ ?class a bxmeta:Axiom }}
  OPTIONAL {{ ?class bxmeta:propertySchema ?propertySchema }}
  {code_filter}
}}
"""
    )

    from app.core.neo4j_converter import deserialize_property_schema

    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        class_u = URIRef(type_uri(code))
        g.add((class_u, RDF.type, OWL.Class))
        g.add((class_u, RDFS.label, Literal(str(row.get("label") or code))))
        schema = deserialize_property_schema(row.get("propertySchema"))
        shape_u = URIRef(shape_uri(code))
        g.add((shape_u, RDF.type, SH.NodeShape))
        g.add((shape_u, SH.targetClass, class_u))
        for pname, pdef in (schema or {}).items():
            if hasattr(pdef, "model_dump"):
                pdef = pdef.model_dump()
            if not isinstance(pdef, dict):
                continue
            from app.ontology.constants import datatype_prop_uri

            prop_u = URIRef(datatype_prop_uri(code, pname))
            ptype = str(pdef.get("type") or "string")
            xsd = URIRef(xsd_for_prop_type(ptype))
            g.add((prop_u, RDF.type, OWL.DatatypeProperty))
            g.add((prop_u, RDFS.domain, class_u))
            g.add((prop_u, RDFS.range, xsd))
            # blank node property shape
            from rdflib import BNode

            bn = BNode()
            g.add((shape_u, SH.property, bn))
            g.add((bn, SH.path, prop_u))
            g.add((bn, SH.datatype, xsd))
            if pdef.get("required"):
                g.add((bn, SH.minCount, Literal(1)))
            g.add((bn, SH.name, Literal(pname)))

    # altLabels
    alt_rows = await graphdb.query(
        f"""
{SHACL_PREFIXES}
SELECT ?code ?alt WHERE {{
  ?c a owl:Class ; bxmeta:code ?code ; skos:altLabel ?alt .
  {code_filter}
}}
"""
    )
    for row in alt_rows:
        code = str(row.get("code") or "")
        alt = str(row.get("alt") or "")
        if code and alt:
            g.add((URIRef(type_uri(code)), SKOS.altLabel, Literal(alt)))

    return g.serialize(format="turtle")


def _q(val: str) -> str:
    import json

    return json.dumps(val, ensure_ascii=False)


async def export_ontology_ttl(graphdb: Any) -> str:
    """导出完整 TBox Turtle（类/关系/shape/别名）。"""
    ttl = await build_shapes_graph_turtle(graphdb, class_code=None)
    # 追加 ObjectProperty
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import OWL, RDF, RDFS

    g = Graph()
    g.parse(data=ttl, format="turtle")
    rows = await graphdb.query(
        f"""
{SHACL_PREFIXES}
SELECT ?code ?label ?domain ?range WHERE {{
  ?prop a owl:ObjectProperty ; bxmeta:code ?code ; rdfs:label ?label .
  OPTIONAL {{ ?prop rdfs:domain ?d . ?d bxmeta:code ?domain }}
  OPTIONAL {{ ?prop rdfs:range ?r . ?r bxmeta:code ?range }}
}}
"""
    )
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        prop_u = URIRef(type_uri(code))
        g.add((prop_u, RDF.type, OWL.ObjectProperty))
        g.add((prop_u, RDFS.label, Literal(str(row.get("label") or code))))
        if row.get("domain"):
            g.add((prop_u, RDFS.domain, URIRef(type_uri(str(row["domain"])))))
        if row.get("range"):
            g.add((prop_u, RDFS.range, URIRef(type_uri(str(row["range"])))))
    return g.serialize(format="turtle")
