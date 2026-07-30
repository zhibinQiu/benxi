"""本体 TBox LLM 发现：候选预览 + 确认写入 GraphDB。

与 KG 实例抽取解耦：本模块只处理概念/关系类型（TBox），不写 Neo4j ABox。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from io import StringIO
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, forbidden
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.models.org import User
from app.schemas.ontology import (
    PropertySchema,
    RelationTypeIn,
)
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)

_MAX_NEW_ENTITY_TYPES = 8
_MAX_NEW_RELATION_TYPES = 10
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_INSTANCE_CODE_RE = re.compile(
    r"("
    r"\d{2,}"
    r"|_v\d+"
    r"|gb[_/]?t?_?\d+"
    r"|iso_?\d+"
    r")"
)
_INSTANCE_LABEL_RE = re.compile(
    r"("
    r"\d{4}"
    r"|第[一二三四五六七八九十\d]+[号章条款]"
    r"|有限公司|股份公司|集团有限"
    r")"
)

ONTOLOGY_DISCOVERY_SYSTEM = """You are an ontology engineer building a TBox (schema), NOT an ABox (instances).

From the document, propose NEW abstract CONCEPT classes and RELATION types between concepts.
Do NOT propose concrete examples, named individuals, or specific cases as entity types.

## Existing entity types (do NOT duplicate)
{existing_entity_types}

## Existing relation types (do NOT duplicate)
{existing_relation_types}

## Output JSON only
{{
  "entity_types": [
    {{
      "code": "snake_case_code",
      "label": "Chinese or English class label",
      "description": "one-line meaning of the CONCEPT class",
      "parent_code": null,
      "properties": [{{"name": "prop", "type": "string", "required": false, "description": ""}}]
    }}
  ],
  "relation_types": [
    {{
      "code": "snake_case_code",
      "label": "label",
      "domain_types": ["entity_type_code"],
      "range_types": ["entity_type_code"],
      "transitive": false,
      "symmetric": false
    }}
  ]
}}

## Hard rules (TBox vs ABox)
1. entity_types MUST be abstract classes / categories (e.g. enterprise, device, emission_source, regulation)
2. NEVER propose named individuals, proper nouns, specific organizations, people, products, document titles, or numeric cases as entity_types
   - BAD (instance mistaken as class): "huawei", "zhang_san", "report_2024", "boiler_3", "gb_t_32151"
   - GOOD (concept class): "enterprise", "person", "report", "boiler", "national_standard"
3. If the text mentions a specific example, map it to an existing or new ABSTRACT class; leave the example for instance extraction later
4. Prefer extending existing types over inventing near-duplicates
5. Propose only types clearly supported by the document; no speculation
6. code must match ^[a-z][a-z0-9_]*$ and be a common noun / category, not a proper name
7. relation domain_types / range_types must reference existing codes OR newly proposed entity type codes
8. At most {max_entity_types} entity types and {max_relation_types} relation types
9. Output JSON only, no markdown
"""


def looks_like_instance_type(code: str, label: str) -> bool:
    """启发式：候选更像具名实例而非抽象概念类时返回 True。"""
    c = (code or "").strip().lower()
    lab = (label or "").strip()
    if not c:
        return True
    if len(c) > 40 or c.count("_") >= 5:
        return True
    if _INSTANCE_CODE_RE.search(c):
        return True
    if lab and _INSTANCE_LABEL_RE.search(lab):
        return True
    if len(lab) > 24 and ("《" in lab or "»" in lab or " " in lab):
        return True
    return False


def clip_text(text: str, max_chars: int | None = None) -> str:
    settings = get_settings()
    limit = max(2000, int(max_chars or settings.kg_extraction_max_chars or 10000))
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    head = body[: int(limit * 0.7)]
    tail = body[-int(limit * 0.25) :]
    return f"{head}\n\n...（中间省略）...\n\n{tail}"


def extract_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("模型未返回内容")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("无法解析模型返回的 JSON")


def format_entity_types_for_prompt(entity_types: list[Any]) -> str:
    buf = StringIO()
    for et in entity_types:
        required = [
            k
            for k, v in (et.property_schema or {}).items()
            if getattr(v, "required", False)
        ]
        req_str = f" [required: {', '.join(required)}]" if required else ""
        buf.write(f"- {et.code} ({et.label}){req_str}\n")
    return buf.getvalue()


def format_relation_types_for_prompt(relation_types: list[Any]) -> str:
    buf = StringIO()
    for rt in relation_types:
        domain = f" domain:{rt.domain_types}" if rt.domain_types else ""
        range_ = f" range:{rt.range_types}" if rt.range_types else ""
        flags = []
        if rt.transitive:
            flags.append("transitive")
        if rt.symmetric:
            flags.append("symmetric")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        buf.write(f"- {rt.code} ({rt.label}){domain}{range_}{flag_str}\n")
    return buf.getvalue()


def _parse_properties(raw: Any) -> dict[str, PropertySchema]:
    prop_schema: dict[str, PropertySchema] = {}
    if not isinstance(raw, list):
        return prop_schema
    for p in raw[:12]:
        if not isinstance(p, dict):
            continue
        pname = str(p.get("name") or "").strip()
        if not _CODE_RE.match(pname):
            continue
        ptype = str(p.get("type") or "string")
        if ptype not in {"string", "number", "date", "boolean", "text", "url"}:
            ptype = "string"
        prop_schema[pname] = PropertySchema(
            type=ptype,
            required=bool(p.get("required")),
            description=str(p.get("description") or "")[:200],
        )
    return prop_schema


async def _build_entity_catalog(ontology: OntologyService) -> list[dict[str, Any]]:
    existing_list = await ontology.list_entity_types(include_counts=False)
    catalog: list[dict[str, Any]] = []
    for et in existing_list:
        alts = await ontology._store.list_alt_labels(et.code)
        catalog.append({"code": et.code, "label": et.label, "alt_labels": alts})
    return catalog


def _classify_entity_candidate(
    *,
    code: str,
    label: str,
    existing_et: set[str],
    catalog: list[dict[str, Any]],
) -> tuple[str, str | None, str]:
    """返回 (action, merge_into, note)。action: create|merge|exists|skip。"""
    from app.ontology.synonym_merge import (
        builtin_canonical_for_label,
        resolve_concept_against_catalog,
    )

    if looks_like_instance_type(code, label):
        return "skip", None, "疑似实例而非抽象概念"
    if code in existing_et:
        return "exists", code, "标识已存在"
    syn = builtin_canonical_for_label(label) or builtin_canonical_for_label(code)
    if syn and syn in existing_et:
        return "merge", syn, f"同义映射到已有概念 {syn}"
    match = resolve_concept_against_catalog(
        code=code, label=label, existing=catalog
    )
    if match:
        return "merge", match.canonical_code, f"合并到已有概念 {match.canonical_code}"
    return "create", None, "将新建概念"


async def discover_ontology_candidates(
    ontology: OntologyService,
    *,
    title: str,
    text: str,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """LLM 发现 TBox 候选；不写库。"""
    if not is_configured():
        raise bad_request("未配置大模型，无法发现本体")

    clipped = clip_text(text, max_chars)
    if len(clipped) < 50:
        raise bad_request("正文过短，无法发现本体（至少约 50 字）")

    entity_types = await ontology.list_entity_types(include_counts=False)
    relation_types = await ontology.list_relation_types(include_counts=False)
    existing_et = {et.code for et in entity_types}
    existing_rt = {rt.code for rt in relation_types}
    catalog = await _build_entity_catalog(ontology)

    system = ONTOLOGY_DISCOVERY_SYSTEM.format(
        existing_entity_types=format_entity_types_for_prompt(entity_types) or "(none)",
        existing_relation_types=format_relation_types_for_prompt(relation_types)
        or "(none)",
        max_entity_types=_MAX_NEW_ENTITY_TYPES,
        max_relation_types=_MAX_NEW_RELATION_TYPES,
    )
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Document title: {title or 'untitled'}\n\nBody:\n{clipped}",
            },
        ],
        temperature=0.1,
        timeout=90.0,
    )
    if not raw:
        raise bad_request("大模型未返回内容")

    try:
        data = extract_json(raw)
    except ValueError as exc:
        raise bad_request(f"本体发现结果解析失败: {exc}") from exc

    candidate_ets = data.get("entity_types") if isinstance(data, dict) else []
    candidate_rts = data.get("relation_types") if isinstance(data, dict) else []
    if not isinstance(candidate_ets, list):
        candidate_ets = []
    if not isinstance(candidate_rts, list):
        candidate_rts = []

    entity_out: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    proposed_et: set[str] = set()

    for item in candidate_ets[:_MAX_NEW_ENTITY_TYPES]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().lower()
        label = str(item.get("label") or code).strip()[:128]
        if not _CODE_RE.match(code):
            skipped.append(
                {"kind": "entity_type", "code": code, "label": label, "reason": "非法 code"}
            )
            continue
        action, merge_into, note = _classify_entity_candidate(
            code=code,
            label=label,
            existing_et=existing_et | proposed_et,
            catalog=catalog,
        )
        if action == "skip":
            skipped.append(
                {"kind": "entity_type", "code": code, "label": label, "reason": note}
            )
            continue
        parent = str(item.get("parent_code") or "").strip().lower() or None
        if parent and not _CODE_RE.match(parent):
            parent = None
        props = _parse_properties(item.get("properties"))
        row = {
            "code": code,
            "label": label or code,
            "description": str(item.get("description") or "")[:300],
            "parent_code": parent,
            "properties": [
                {
                    "name": k,
                    "type": v.type,
                    "required": v.required,
                    "description": v.description,
                }
                for k, v in props.items()
            ],
            "action": action,
            "merge_into": merge_into,
            "note": note,
            "selected": action in ("create", "merge"),
        }
        entity_out.append(row)
        if action == "create":
            proposed_et.add(code)

    available_et = existing_et | {e["code"] for e in entity_out if e["action"] == "create"}
    for e in entity_out:
        if e["action"] == "merge" and e.get("merge_into"):
            available_et.add(str(e["merge_into"]))

    relation_out: list[dict[str, Any]] = []
    for item in candidate_rts[:_MAX_NEW_RELATION_TYPES]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().lower()
        label = str(item.get("label") or code).strip()[:128]
        if not _CODE_RE.match(code):
            skipped.append(
                {
                    "kind": "relation_type",
                    "code": code,
                    "label": label,
                    "reason": "非法 code",
                }
            )
            continue
        if code in existing_rt:
            relation_out.append(
                {
                    "code": code,
                    "label": label or code,
                    "domain_types": [],
                    "range_types": [],
                    "transitive": bool(item.get("transitive")),
                    "symmetric": bool(item.get("symmetric")),
                    "action": "exists",
                    "note": "关系类型已存在",
                    "selected": False,
                }
            )
            continue
        domains = [
            str(x).strip()
            for x in (item.get("domain_types") or [])
            if str(x).strip() in available_et
        ]
        ranges = [
            str(x).strip()
            for x in (item.get("range_types") or [])
            if str(x).strip() in available_et
        ]
        if not domains or not ranges:
            skipped.append(
                {
                    "kind": "relation_type",
                    "code": code,
                    "label": label,
                    "reason": "domain/range 无法落到已有或拟新建概念",
                }
            )
            continue
        relation_out.append(
            {
                "code": code,
                "label": label or code,
                "domain_types": domains,
                "range_types": ranges,
                "transitive": bool(item.get("transitive")),
                "symmetric": bool(item.get("symmetric")),
                "action": "create",
                "note": "将新建关系类型",
                "selected": True,
            }
        )

    return {
        "entity_types": entity_out,
        "relation_types": relation_out,
        "skipped": skipped,
        "stats": {
            "candidates": len(candidate_ets) + len(candidate_rts),
            "entity_candidates": len(entity_out),
            "relation_candidates": len(relation_out),
            "skipped": len(skipped),
        },
    }


async def apply_ontology_candidates(
    ontology: OntologyService,
    *,
    entity_types: list[dict[str, Any]] | None = None,
    relation_types: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """将用户勾选的候选写入 GraphDB。"""
    stats = {
        "entity_types_created": 0,
        "entity_types_merged": 0,
        "relation_types_created": 0,
        "skipped": 0,
    }
    existing = await ontology.list_entity_types(include_counts=False)
    existing_et = {et.code for et in existing}
    existing_rt = {
        rt.code for rt in await ontology.list_relation_types(include_counts=False)
    }
    created_codes: set[str] = set()

    for item in entity_types or []:
        if not isinstance(item, dict):
            stats["skipped"] += 1
            continue
        code = str(item.get("code") or "").strip().lower()
        label = str(item.get("label") or code).strip()[:128]
        action = str(item.get("action") or "create").strip().lower()
        if action == "exists" or not _CODE_RE.match(code):
            stats["skipped"] += 1
            continue
        if looks_like_instance_type(code, label):
            stats["skipped"] += 1
            continue
        props = _parse_properties(item.get("properties"))
        try:
            if action == "merge":
                merge_into = str(item.get("merge_into") or "").strip().lower()
                if merge_into and merge_into in existing_et:
                    et = await ontology.get_entity_type(merge_into, include_counts=False)
                    if et and label and label != et.label:
                        await ontology._store.add_alt_label(et.code, label)
                    stats["entity_types_merged"] += 1
                    continue
            et_out, created = await ontology.resolve_or_merge_entity_type(
                code=code,
                label=label or code,
                property_schema=props,
            )
            code = et_out.code
            if created:
                parent = str(item.get("parent_code") or "").strip().lower()
                if parent and parent in existing_et | created_codes:
                    try:
                        await ontology.set_subclass_of(code, parent)
                    except Exception as exc:
                        logger.debug("subClassOf 写入失败 %s⊑%s: %s", code, parent, exc)
                created_codes.add(code)
                existing_et.add(code)
                stats["entity_types_created"] += 1
            else:
                existing_et.add(code)
                stats["entity_types_merged"] += 1
        except Exception as exc:
            logger.debug("跳过候选实体类型 %s: %s", code, exc)
            stats["skipped"] += 1

    for item in relation_types or []:
        if not isinstance(item, dict):
            stats["skipped"] += 1
            continue
        code = str(item.get("code") or "").strip().lower()
        label = str(item.get("label") or code).strip()[:128]
        action = str(item.get("action") or "create").strip().lower()
        if action != "create" or not _CODE_RE.match(code) or code in existing_rt:
            stats["skipped"] += 1
            continue
        domains = [
            str(x).strip()
            for x in (item.get("domain_types") or [])
            if str(x).strip() in existing_et
        ]
        ranges = [
            str(x).strip()
            for x in (item.get("range_types") or [])
            if str(x).strip() in existing_et
        ]
        if not domains or not ranges:
            stats["skipped"] += 1
            continue
        try:
            await ontology.create_relation_type(
                RelationTypeIn(
                    code=code,
                    label=label or code,
                    domain_types=domains,
                    range_types=ranges,
                    transitive=bool(item.get("transitive")),
                    symmetric=bool(item.get("symmetric")),
                    sort_order=200,
                )
            )
            existing_rt.add(code)
            stats["relation_types_created"] += 1
        except Exception as exc:
            logger.debug("跳过候选关系类型 %s: %s", code, exc)
            stats["skipped"] += 1

    if stats["entity_types_created"] or stats["relation_types_created"]:
        try:
            await ontology.rebuild_shapes_for_all()
        except Exception as exc:
            logger.warning("本体 shapes 重建失败: %s", exc)

    return stats


async def discover_and_merge_ontology(
    ontology: OntologyService,
    *,
    title: str,
    text: str,
) -> dict[str, Any]:
    """KG 兼容路径：发现全部可写候选并立即写入（无人工预览）。"""
    try:
        discovered = await discover_ontology_candidates(
            ontology, title=title, text=text
        )
    except Exception as exc:
        logger.warning("本体发现失败，跳过合并: %s", exc)
        return {
            "entity_types_created": 0,
            "relation_types_created": 0,
            "candidates": 0,
        }

    to_apply_et = [
        e
        for e in discovered.get("entity_types") or []
        if e.get("action") in ("create", "merge") and e.get("selected", True)
    ]
    to_apply_rt = [
        r
        for r in discovered.get("relation_types") or []
        if r.get("action") == "create" and r.get("selected", True)
    ]
    stats = await apply_ontology_candidates(
        ontology,
        entity_types=to_apply_et,
        relation_types=to_apply_rt,
    )
    stats["candidates"] = int((discovered.get("stats") or {}).get("candidates") or 0)
    return stats


def _load_document_text(
    db: Session,
    user: User,
    document_id: uuid.UUID,
) -> tuple[str, str]:
    """读取文档标题与正文。"""
    from app.core.document_scope import can_query_document
    from app.services.compare_service import get_document_content_for_version
    from app.services.document_service import get_document

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise bad_request(f"文档不存在: {document_id}")
    if not can_query_document(db, user, doc):
        raise forbidden("无权读取该文档")

    title = (doc.title or "").strip() or "未命名文档"
    full_text = ""
    try:
        if doc.current_version_id:
            payload = get_document_content_for_version(
                db, user, doc.id, doc.current_version_id
            )
            full_text = str(payload.get("full_text") or "").strip()
    except Exception as exc:
        logger.debug("版本正文解析失败 doc=%s: %s", document_id, exc)

    if len(full_text) < 50:
        from app.services.agent_document_service import read_document_content_for_agent

        payload = read_document_content_for_agent(
            db,
            user,
            document_id=doc.id,
            max_chars=get_settings().kg_extraction_max_chars or 10000,
        )
        full_text = str(payload.get("full_text") or "").strip()
        title = str(payload.get("title") or title)

    return title, full_text


async def discover_ontology_from_documents(
    ontology: OntologyService,
    db: Session,
    user: User,
    *,
    document_ids: list[uuid.UUID],
    max_chars: int | None = None,
) -> dict[str, Any]:
    """从多份文档拼正文后发现 TBox 候选（同步、不写库）。"""
    if not document_ids:
        raise bad_request("请提供 document_ids")
    if len(document_ids) > 20:
        raise bad_request("单次最多 20 份文档")

    parts: list[str] = []
    titles: list[str] = []
    for did in document_ids:
        title, text = _load_document_text(db, user, did)
        titles.append(title)
        if text.strip():
            parts.append(f"# {title}\n\n{text.strip()}")
    combined = "\n\n---\n\n".join(parts)
    if len(combined.strip()) < 50:
        raise bad_request("所选文档无可抽取正文")

    result = await discover_ontology_candidates(
        ontology,
        title="；".join(titles)[:120] or "documents",
        text=combined,
        max_chars=max_chars,
    )
    result["document_count"] = len(document_ids)
    result["titles"] = titles
    return result
