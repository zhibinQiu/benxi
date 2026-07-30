"""知识图谱 LLM 抽取：本体发现 + 本体约束下的实体/关系抽取。

流程：
1. （可选）从正文发现候选实体类型 / 关系类型，合并进 GraphDB 全局本体
2. 使用完整本体约束 LLM 抽取实例实体与关系
3. 写入前硬过滤：未知类型、domain/range 不合法的项一律丢弃
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from sqlalchemy.orm import Session

    from app.models.document import Document, DocumentVersion
    from app.models.org import User

from app.core.neo4j import make_neo4j_base_service
from app.config import get_settings
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.schemas.kg import EntityIn, RelationIn
from app.services.kg_service import KgService
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)

_MAX_ENTITIES = 24
_MAX_RELATIONS = 32
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

EXTRACTION_SYSTEM_V2 = """You are an ontology-constrained knowledge graph extractor. Extract entities and relations from the document STRICTLY using the provided ontology.

## Allowed entity types
{entity_types_json}

## Allowed relation types (with domain -> range constraints)
{relation_types_json}

## Output JSON only
{{
  "entities": [
    {{"type_code": "allowed_code", "name": "entity name", "description": "one sentence"}}
  ],
  "relations": [
    {{
      "type_code": "allowed_code",
      "from_name": "source entity name",
      "to_name": "target entity name",
      "description": ""
    }}
  ]
}}

## Hard constraints
1. Extract only entities explicitly present in the text; never invent
2. entity.type_code MUST be one of the allowed entity types
3. relation.type_code MUST be one of the allowed relation types
4. relation endpoints MUST satisfy domain -> range of that relation type
5. Entity names concise (<=40 chars); each entity once
6. At most {max_entities} entities and {max_relations} relations
7. If an observed fact cannot fit the ontology, omit it
8. Output JSON only, no markdown
"""


def _run_coro_sync(coro: Any, *, timeout: float = 300.0) -> Any:
    """在同步上下文执行 async 协程（上传后处理 / Celery worker）。"""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=timeout)


def extract_kg_for_document_upload(
    db: Session,
    user: User,
    document: Document,
    version: DocumentVersion | None = None,
    *,
    force: bool = True,
    discover_ontology: bool = True,
) -> dict[str, Any]:
    """文档上传后抽取：本体发现 + 本体约束的实体/关系写入。

    Args:
        force: True 时忽略已抽取标记（每次上传/新版本都应重抽）。
    """
    settings = get_settings()
    if not settings.kg_extraction_enabled or not is_configured():
        return {"skipped": True, "reason": "kg_extraction_disabled"}

    doc_id = str(document.id)
    user_id = str(user.id)

    async def _already() -> bool:
        from app.core.neo4j import get_neo4j

        driver = await get_neo4j()
        return await document_content_extracted(driver, doc_id)

    if not force and _run_coro_sync(_already()):
        return {"skipped": True, "reason": "already_extracted"}

    # 优先当前版本解析正文；失败则走 agent 读取（PageIndex / 对比解析）
    full_text = ""
    title = (document.title or "").strip() or "未命名文档"
    try:
        from app.services.compare_service import get_document_content_for_version

        if version is not None:
            payload = get_document_content_for_version(db, user, document.id, version.id)
            full_text = str(payload.get("full_text") or "").strip()
    except Exception as exc:
        logger.debug("版本正文解析失败 doc=%s: %s", doc_id, exc)

    if len(full_text) < 50:
        try:
            from app.services.agent_document_service import read_document_content_for_agent

            payload = read_document_content_for_agent(
                db,
                user,
                document_id=document.id,
                max_chars=settings.kg_extraction_max_chars or 10000,
            )
            full_text = str(payload.get("full_text") or "").strip()
            title = str(payload.get("title") or title)
        except Exception as exc:
            logger.info("上传后抽取：无法读取正文 doc=%s (%s)", doc_id, exc)
            return {"skipped": True, "reason": "text_unavailable", "error": str(exc)}

    if len(full_text) < 50:
        return {"skipped": True, "reason": "text_too_short"}

    async def _ensure_doc_entity_and_extract() -> dict[str, Any]:
        from app.core.neo4j import get_neo4j

        driver = await get_neo4j()
        base = make_neo4j_base_service(driver)
        exists = await base.run_single(
            "MATCH (e:Entity {source_document_id: $sid, type_code: 'doc'}) "
            "RETURN e.id AS id LIMIT 1",
            {"sid": doc_id},
        )
        if not exists:
            await base.run(
                "CREATE (e:Entity {id: $id, type_code: 'doc', name: $name, "
                "description: $desc, source_type: 'system', "
                "source_document_id: $sid, owner_id: $owner, created_by: $owner, "
                "created_at: datetime(), updated_at: datetime(), "
                "content_extracted: false})",
                {
                    "id": str(uuid.uuid4()),
                    "name": title,
                    "desc": (document.description or "")[:1000],
                    "sid": doc_id,
                    "owner": user_id,
                },
            )
        elif force:
            await base.run(
                "MATCH (e:Entity {source_document_id: $sid, type_code: 'doc'}) "
                "SET e.content_extracted = false, e.updated_at = datetime()",
                {"sid": doc_id},
            )

        return await extract_kg_from_text_v2(
            driver,
            title=title,
            text=full_text,
            user_id=user_id,
            source_type="extraction",
            source_id=doc_id,
            discover_ontology=discover_ontology,
        )

    try:
        result = _run_coro_sync(_ensure_doc_entity_and_extract(), timeout=360.0)
        logger.info(
            "上传后 KG 抽取完成 doc=%s version=%s result=%s",
            doc_id,
            getattr(version, "id", None),
            {
                k: result.get(k)
                for k in (
                    "skipped",
                    "reason",
                    "entities_created",
                    "relations_created",
                    "ontology",
                )
            },
        )
        return result
    except Exception as exc:
        logger.exception("上传后 KG 抽取失败 doc=%s: %s", doc_id, exc)
        return {"skipped": True, "reason": "extract_failed", "error": str(exc)}


async def extract_kg_from_text_v2(
    driver: AsyncDriver,
    *,
    title: str,
    text: str,
    user_id: str,
    source_type: str = "manual",
    source_id: str | None = None,
    discover_ontology: bool = True,
) -> dict[str, Any]:
    """两阶段抽取：可选本体发现 → 本体约束实例抽取 → Neo4j 写入。"""
    settings = get_settings()
    if not settings.kg_extraction_enabled or not is_configured():
        return {"skipped": True, "reason": "kg_extraction_disabled"}

    text = (text or "").strip()
    if len(text) < 50:
        return {"skipped": True, "reason": "text_too_short"}

    from app.services.ontology_factory import get_ontology_service

    ontology = await get_ontology_service()
    clipped = _clip_text(text, settings.kg_extraction_max_chars or 10000)

    ontology_stats: dict[str, Any] = {
        "entity_types_created": 0,
        "relation_types_created": 0,
        "candidates": 0,
    }
    if discover_ontology:
        ontology_stats = await _discover_and_merge_ontology(
            ontology,
            title=title,
            text=clipped,
        )

    entity_types = await ontology.list_entity_types(include_counts=False)
    relation_types = await ontology.list_relation_types(include_counts=False)
    if not entity_types:
        return {
            "skipped": True,
            "reason": "ontology_empty",
            "error": "本体为空，无法约束抽取",
            "ontology": ontology_stats,
        }

    allowed_entity_codes = {et.code for et in entity_types}
    relation_by_code = {rt.code: rt for rt in relation_types}

    system = EXTRACTION_SYSTEM_V2.format(
        entity_types_json=_format_entity_types_for_prompt(entity_types),
        relation_types_json=_format_relation_types_for_prompt(relation_types),
        max_entities=_MAX_ENTITIES,
        max_relations=_MAX_RELATIONS,
    )
    user_content = (
        f"Document title: {title or 'untitled'}\n\n"
        f"Body:\n{clipped}"
    )
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        timeout=120.0,
    )
    if not raw:
        return {
            "skipped": True,
            "reason": "llm_failed",
            "error": "模型未返回内容",
            "ontology": ontology_stats,
        }

    try:
        data = _extract_json(raw)
    except ValueError as exc:
        return {
            "skipped": True,
            "reason": "llm_failed",
            "error": str(exc),
            "ontology": ontology_stats,
        }

    entities_raw = _normalize_entities(data, allowed_entity_codes)
    relations_raw = _normalize_relations(data, relation_by_code, entities_raw)

    dropped = int(data.get("_dropped_entities") or 0) + int(data.get("_dropped_relations") or 0)
    validation_errors = await _validate_extraction(
        ontology, entities_raw, relations_raw
    )
    # 硬过滤：仅保留通过校验的项
    entities_ok, relations_ok, filter_errors = _hard_filter_by_ontology(
        entities_raw, relations_raw, allowed_entity_codes, relation_by_code
    )
    validation_errors.extend(filter_errors)

    if not entities_ok:
        return {
            "skipped": True,
            "reason": "no_valid_entities",
            "error": "未解析到符合本体约束的实体",
            "validation_errors": validation_errors,
            "ontology": ontology_stats,
            "dropped": dropped,
        }

    kg = KgService(driver)
    name_to_id: dict[str, str] = {}
    entities_created = 0
    entities_linked = 0
    relations_created = 0
    doc_links_created = 0

    doc_entity_id: str | None = None
    if source_id:
        doc_entity_id = await _ensure_source_doc_entity(
            driver,
            document_id=source_id,
            title=title,
            user_id=user_id,
        )

    for ent in entities_ok:
        existing = await kg.find_entity_by_identity(
            user_id, type_code=ent["type_code"], name=ent["name"]
        )
        if existing:
            name_to_id[ent["name"]] = existing.id
            entities_linked += 1
        else:
            try:
                result = await kg.create_entity(
                    EntityIn(
                        type_code=ent["type_code"],
                        name=ent["name"],
                        # 抽取只落关键描述摘要，明细属性不入图
                        description=(ent.get("description") or "")[:200],
                        source_type="extraction",
                        source_document_id=source_id,
                    ),
                    user_id,
                )
                name_to_id[ent["name"]] = result.id
                entities_created += 1
            except ValueError as exc:
                logger.warning("实体抽取创建失败: %s", exc)
                validation_errors.append(str(exc))
                continue

        # 文档实体 → 抽取/复用实体：建立 references，避免重复边
        if doc_entity_id and name_to_id.get(ent["name"]):
            linked = await _link_doc_to_entity(
                kg,
                doc_entity_id=doc_entity_id,
                entity_id=name_to_id[ent["name"]],
                user_id=user_id,
                doc_title=title,
            )
            if linked:
                doc_links_created += 1

    for rel in relations_ok:
        from_id = name_to_id.get(rel["from_name"])
        to_id = name_to_id.get(rel["to_name"])
        if not from_id or not to_id:
            continue
        try:
            await kg.create_relation(
                RelationIn(
                    type_code=rel["type_code"],
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    description=rel.get("description", ""),
                ),
                user_id,
            )
            relations_created += 1
        except ValueError as exc:
            msg = str(exc)
            if "相同关系已存在" in msg:
                continue
            logger.debug("关系抽取创建跳过: %s", exc)
            validation_errors.append(msg)

    # 标记文档已完成内容抽取（便于批量跳过）
    if source_id and (entities_created or relations_created or entities_linked or doc_links_created):
        await _mark_document_extracted(driver, source_id, user_id)

    return {
        "skipped": False,
        "entities_created": entities_created,
        "entities_linked": entities_linked,
        "relations_created": relations_created,
        "doc_links_created": doc_links_created,
        "validation_errors": validation_errors[:50],
        "ontology": ontology_stats,
        "dropped": dropped + len(filter_errors),
    }


async def _discover_and_merge_ontology(
    ontology: OntologyService,
    *,
    title: str,
    text: str,
) -> dict[str, Any]:
    """从正文发现候选本体并合并到 GraphDB（委托 ontology_extraction_service）。"""
    from app.services.ontology_extraction_service import discover_and_merge_ontology

    return await discover_and_merge_ontology(ontology, title=title, text=text)


async def _find_entity_by_name(driver: AsyncDriver, name: str, user_id: str) -> str | None:
    """精确名或别名命中（跨类型兜底；优先用 KgService.find_entity_by_identity）。"""
    from app.ontology.synonym_merge import names_match

    base = make_neo4j_base_service(driver)
    records = await base.run_and_collect(
        """
        MATCH (e:Entity)
        WHERE e.owner_id = $owner_id OR e.owner_id IS NULL
        RETURN e.id AS id, e.name AS name, e.aliases AS aliases
        LIMIT 800
        """,
        {"owner_id": user_id},
    )
    for rec in records:
        if names_match(str(rec.get("name") or ""), name):
            return rec.get("id")
        try:
            aliases = json.loads(rec.get("aliases") or "[]")
        except (TypeError, json.JSONDecodeError):
            aliases = []
        if isinstance(aliases, list):
            for a in aliases:
                if names_match(str(a), name):
                    return rec.get("id")
    return None


async def _ensure_source_doc_entity(
    driver: AsyncDriver,
    *,
    document_id: str,
    title: str,
    user_id: str,
) -> str | None:
    """确保来源文档实体存在，并用文档标题作为 name（可更新）。"""
    base = make_neo4j_base_service(driver)
    name = (title or "").strip() or "未命名文档"
    row = await base.run_single(
        "MATCH (e:Entity {source_document_id: $sid, type_code: 'doc'}) "
        "RETURN e.id AS id LIMIT 1",
        {"sid": document_id},
    )
    if row and row.get("id"):
        await base.run(
            "MATCH (e:Entity {id: $id}) "
            "SET e.name = $name, e.updated_at = datetime()",
            {"id": row["id"], "name": name},
        )
        return str(row["id"])
    eid = str(uuid.uuid4())
    await base.run(
        "CREATE (e:Entity {id: $id, type_code: 'doc', name: $name, "
        "description: $desc, source_type: 'system', "
        "source_document_id: $sid, owner_id: $owner, created_by: $owner, "
        "created_at: datetime(), updated_at: datetime(), "
        "content_extracted: false})",
        {
            "id": eid,
            "name": name,
            "desc": "",
            "sid": document_id,
            "owner": user_id,
        },
    )
    return eid


async def _link_doc_to_entity(
    kg: KgService,
    *,
    doc_entity_id: str,
    entity_id: str,
    user_id: str,
    doc_title: str = "",
) -> bool:
    """文档 —references→ 实体；已存在则跳过。"""
    if not doc_entity_id or not entity_id or doc_entity_id == entity_id:
        return False
    try:
        await kg.create_relation(
            RelationIn(
                type_code="references",
                from_entity_id=doc_entity_id,
                to_entity_id=entity_id,
                description=f"来源文档: {doc_title}"[:200] if doc_title else "文档抽取关联",
            ),
            user_id,
        )
        return True
    except ValueError as exc:
        if "相同关系已存在" in str(exc):
            return False
        # references 未进本体时降级：不阻断抽取
        logger.debug("文档关联跳过: %s", exc)
        return False


async def _mark_document_extracted(
    driver: AsyncDriver, document_id: str, user_id: str
) -> None:
    """在文档实体上标记 content_extracted=true。"""
    base = make_neo4j_base_service(driver)
    await base.run(
        """
        MATCH (e:Entity {source_document_id: $sid})
        WHERE e.type_code = 'doc' AND (e.owner_id = $owner OR e.owner_id IS NULL)
        SET e.content_extracted = true, e.updated_at = datetime()
        """,
        {"sid": document_id, "owner": user_id},
    )


async def document_content_extracted(
    driver: AsyncDriver, document_id: str
) -> bool:
    """文档是否已完成内容抽取。"""
    base = make_neo4j_base_service(driver)
    rows = await base.run_and_collect(
        """
        MATCH (e:Entity {source_document_id: $sid})
        WHERE e.content_extracted = true
           OR (e.source_type = 'extraction' AND e.type_code <> 'doc')
        RETURN count(e) AS cnt
        """,
        {"sid": document_id},
    )
    return bool(rows and int(rows[0].get("cnt") or 0) > 0)


async def _validate_extraction(
    ontology: OntologyService,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    entity_type_map = {ent["name"]: ent["type_code"] for ent in entities}
    for ent in entities:
        et = await ontology.get_entity_type(ent["type_code"])
        if not et:
            errors.append(f"实体类型 '{ent['type_code']}' 不在本体中")
    for rel in relations:
        rt = await ontology.get_relation_type(rel["type_code"])
        if not rt:
            errors.append(f"关系类型 '{rel['type_code']}' 不在本体中")
            continue
        from_type = entity_type_map.get(rel["from_name"], "")
        to_type = entity_type_map.get(rel["to_name"], "")
        if rt.domain_types and from_type not in rt.domain_types:
            errors.append(
                f"关系 '{rel['type_code']}' 起点 '{rel['from_name']}' "
                f"类型 '{from_type}' 不在 domain {rt.domain_types}"
            )
        if rt.range_types and to_type not in rt.range_types:
            errors.append(
                f"关系 '{rel['type_code']}' 终点 '{rel['to_name']}' "
                f"类型 '{to_type}' 不在 range {rt.range_types}"
            )
    return errors


def _hard_filter_by_ontology(
    entities: list[dict[str, str]],
    relations: list[dict[str, str]],
    allowed_entity_codes: set[str],
    relation_by_code: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    errors: list[str] = []
    entities_ok = [e for e in entities if e["type_code"] in allowed_entity_codes]
    dropped_e = len(entities) - len(entities_ok)
    if dropped_e:
        errors.append(f"丢弃 {dropped_e} 个未知/非法实体类型")

    name_type = {e["name"]: e["type_code"] for e in entities_ok}
    relations_ok: list[dict[str, str]] = []
    for rel in relations:
        rt = relation_by_code.get(rel["type_code"])
        if not rt:
            errors.append(f"丢弃未知关系类型 '{rel['type_code']}'")
            continue
        from_type = name_type.get(rel["from_name"], "")
        to_type = name_type.get(rel["to_name"], "")
        if not from_type or not to_type:
            errors.append(
                f"丢弃关系 '{rel['type_code']}'：端点实体未通过类型校验"
            )
            continue
        if rt.domain_types and from_type not in rt.domain_types:
            errors.append(
                f"丢弃关系 '{rel['type_code']}'：domain 不满足 ({from_type})"
            )
            continue
        if rt.range_types and to_type not in rt.range_types:
            errors.append(
                f"丢弃关系 '{rel['type_code']}'：range 不满足 ({to_type})"
            )
            continue
        relations_ok.append(rel)
    return entities_ok, relations_ok, errors


def _format_entity_types_for_prompt(entity_types: list[Any]) -> str:
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


def _format_relation_types_for_prompt(relation_types: list[Any]) -> str:
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


def _clip_text(text: str, max_chars: int) -> str:
    limit = max(2000, max_chars)
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    head = body[: int(limit * 0.7)]
    tail = body[-int(limit * 0.25) :]
    return f"{head}\n\n...（中间省略）...\n\n{tail}"


def _extract_json(raw: str) -> dict[str, Any]:
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


def _normalize_entities(
    data: dict[str, Any], allowed_codes: set[str]
) -> list[dict[str, str]]:
    rows = data.get("entities", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    dropped = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:256]
        if not name or name in seen:
            continue
        type_code = str(item.get("type_code") or "").strip().lower()
        if type_code not in allowed_codes:
            dropped += 1
            continue
        description = str(item.get("description") or "").strip()[:200]
        out.append({"type_code": type_code, "name": name, "description": description})
        seen.add(name)
        if len(out) >= _MAX_ENTITIES:
            break
    data["_dropped_entities"] = dropped
    return out


def _normalize_relations(
    data: dict[str, Any],
    relation_by_code: dict[str, Any],
    entities: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows = data.get("relations", [])
    if not isinstance(rows, list):
        return []
    entity_names = {e["name"] for e in entities}
    out: list[dict[str, str]] = []
    dropped = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        from_name = str(item.get("from_name") or "").strip()
        to_name = str(item.get("to_name") or "").strip()
        type_code = str(item.get("type_code") or "").strip().lower()
        if (
            not from_name
            or not to_name
            or from_name == to_name
            or type_code not in relation_by_code
            or from_name not in entity_names
            or to_name not in entity_names
        ):
            dropped += 1
            continue
        description = str(item.get("description") or "").strip()[:500]
        out.append(
            {
                "type_code": type_code,
                "from_name": from_name,
                "to_name": to_name,
                "description": description,
            }
        )
        if len(out) >= _MAX_RELATIONS:
            break
    data["_dropped_relations"] = dropped
    return out
