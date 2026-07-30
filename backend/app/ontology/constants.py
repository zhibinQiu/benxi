"""本析本体 RDF 命名空间与 URI 工具（全局共享 TBox，无租户隔离）。"""

from __future__ import annotations

BX_NS = "http://benxi.ai/ontology/"
BXMETA_NS = "http://benxi.ai/ontology/meta#"
AXIOM_NS = "http://benxi.ai/ontology/axiom/"
SHAPE_NS = "http://benxi.ai/ontology/shapes/"
PROP_NS = "http://benxi.ai/ontology/prop/"
SHACL_NS = "http://www.w3.org/ns/shacl#"
SKOS_NS = "http://www.w3.org/2004/02/skos/core#"


def type_uri(code: str) -> str:
    """实体/关系类型 code → 全局语义 URI。"""
    return f"{BX_NS}{code}"


def axiom_uri(name: str) -> str:
    return f"{AXIOM_NS}{name}"


def shape_uri(code: str) -> str:
    """实体类型对应的 SHACL NodeShape URI。"""
    return f"{SHAPE_NS}{code}Shape"


def datatype_prop_uri(class_code: str, prop_name: str) -> str:
    """类上数据属性 URI。"""
    return f"{PROP_NS}{class_code}/{prop_name}"


def code_from_uri(uri: str) -> str:
    if uri.startswith(BX_NS):
        return uri[len(BX_NS) :]
    if uri.startswith(AXIOM_NS):
        return uri[len(AXIOM_NS) :]
    if uri.startswith(SHAPE_NS):
        rest = uri[len(SHAPE_NS) :]
        return rest[:-5] if rest.endswith("Shape") else rest
    if uri.startswith(PROP_NS):
        return uri[len(PROP_NS) :]
    return uri
