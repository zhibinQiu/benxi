"""同义词规范化与概念/实体身份解析（应用层合并，不依赖 GraphDB sameAs）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# 内置同义簇：任一标签规范化后命中 → canonical code
_BUILTIN_SYNONYM_CLUSTERS: list[tuple[str, list[str]]] = [
    (
        "carbon_emission",
        [
            "碳排放",
            "碳排放量",
            "二氧化碳排放",
            "co2排放",
            "co2 emission",
            "carbon emission",
            "carbon emissions",
            "ghg emission",
        ],
    ),
    (
        "enterprise",
        ["企业", "公司", "厂商", "enterprise", "company", "firm"],
    ),
    (
        "org",
        ["组织", "机构", "organization", "organisation", "org"],
    ),
    (
        "person",
        ["人员", "员工", "自然人", "person", "employee", "staff"],
    ),
    (
        "regulation",
        ["法规", "标准", "规范", "regulation", "standard", "规范标准"],
    ),
    (
        "metric",
        ["指标", "kpi", "metric", "指标项"],
    ),
    (
        "project",
        ["项目", "工程", "project"],
    ),
    (
        "doc",
        ["文档", "文件", "资料", "document", "doc"],
    ),
]

_ORG_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团有限公司|集团公司|集团|公司|厂|所)$"
)
_WS_RE = re.compile(r"[\s\-_/·•]+")
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def normalize_label(text: str) -> str:
    """规范化显示名，用于同义匹配。"""
    s = unicodedata.normalize("NFKC", (text or "").strip()).lower()
    s = _WS_RE.sub("", s)
    s = _ORG_SUFFIX_RE.sub("", s)
    return s


def normalize_code_candidate(text: str) -> str:
    """将标签转为可能的 snake_case code。"""
    s = unicodedata.normalize("NFKC", (text or "").strip()).lower()
    s = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    # 中文无法直接作 code 时返回空，由调用方用已有匹配
    if re.search(r"[\u4e00-\u9fff]", s):
        return ""
    if s and not s[0].isalpha():
        s = f"c_{s}"
    return s[:64] if s else ""


def builtin_canonical_for_label(label: str) -> str | None:
    """命中内置同义表时返回 canonical code。"""
    key = normalize_label(label)
    if not key:
        return None
    for canonical, aliases in _BUILTIN_SYNONYM_CLUSTERS:
        norms = {normalize_label(a) for a in aliases}
        norms.add(normalize_label(canonical.replace("_", "")))
        if key in norms:
            return canonical
    return None


@dataclass
class ConceptMatch:
    canonical_code: str
    matched_by: str  # code | label | alt_label | synonym | normalized
    add_alt_label: str | None = None


def resolve_concept_against_catalog(
    *,
    code: str,
    label: str,
    existing: list[dict],
) -> ConceptMatch | None:
    """在已有概念目录中解析是否应合并。

    existing 项: {code, label, alt_labels?: list[str]}
    """
    code_l = (code or "").strip().lower()
    label_s = (label or "").strip()
    label_n = normalize_label(label_s)
    by_code = {str(e.get("code") or "").lower(): e for e in existing if e.get("code")}

    if code_l and code_l in by_code:
        return ConceptMatch(canonical_code=code_l, matched_by="code")

    syn = builtin_canonical_for_label(label_s) or builtin_canonical_for_label(code_l)
    if syn and syn in by_code:
        alt = label_s if label_s and normalize_label(label_s) != normalize_label(syn) else None
        return ConceptMatch(canonical_code=syn, matched_by="synonym", add_alt_label=alt)

    for e in existing:
        ec = str(e.get("code") or "")
        if not ec:
            continue
        if label_n and normalize_label(str(e.get("label") or "")) == label_n:
            return ConceptMatch(
                canonical_code=ec,
                matched_by="label",
                add_alt_label=label_s if label_s != e.get("label") else None,
            )
        for alt in e.get("alt_labels") or []:
            if label_n and normalize_label(str(alt)) == label_n:
                return ConceptMatch(canonical_code=ec, matched_by="alt_label")

    # code 与已有 label 规范化相等（如 carbon_emission vs 碳排放量已映射）
    code_as_label = normalize_label(code_l.replace("_", ""))
    if code_as_label:
        for e in existing:
            ec = str(e.get("code") or "")
            if normalize_label(str(e.get("label") or "")) == code_as_label:
                return ConceptMatch(canonical_code=ec, matched_by="normalized")
            if normalize_label(ec.replace("_", "")) == code_as_label:
                return ConceptMatch(canonical_code=ec, matched_by="normalized")

    return None


def should_create_new_code(code: str) -> bool:
    return bool(_CODE_RE.match((code or "").strip().lower()))


def names_match(a: str, b: str) -> bool:
    return normalize_label(a) == normalize_label(b) and bool(normalize_label(a))
