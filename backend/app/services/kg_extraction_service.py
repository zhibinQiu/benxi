"""知识图谱 LLM 实体/关系抽取 — Neo4j / Ontology 版。

从文档正文使用 LLM 抽取实体和关系，写入 Neo4j 图数据库。
抽取过程受本体（Ontology）约束，抽取后自动验证 domain/range。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.agentkit.graph import Neo4jBaseService
from app.config import get_settings
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.schemas.kg import EntityIn, RelationIn
from app.services.kg_service import KgService
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)

_MAX_ENTITIES = 24
_MAX_RELATIONS = 32

EXTRACTION_SYSTEM_V2 = """你是基于本体的知识图谱抽取助手。根据文档正文识别关键实体与关系，输出严格 JSON。

## 本体实体类型（仅限以下）
{entity_types_json}

## 本体关系类型（仅限以下）
{relation_types_json}

## 输出格式
{{"entities": [{{"type_code": "doc", "name": "实体名称", "description": "一句话说明"}}], "relations": [{{"type_code": "references", "from_name": "起点实体名", "to_name": "终点实体名", "description": ""}}]}}

## 规则
1. 只抽取正文中明确出现的实体，不要编造
2. entity.type_code 必须属于上述实体类型
3. relation.type_code 必须属于上述关系类型
4. relation 两端的 entity.type_code 必须满足 domain->range 约束
5. 实体名称简洁（<=40字），同一实体只出现一次
6. 最多 {max_entities} 个实体、{max_relations} 条关系
7. 只输出 JSON，不要 Markdown 代码块"""


async def extract_kg_from_text_v2(
    driver: AsyncDriver,
    *,
    title: str,
    text: str,
    user_id: str,
    source_type: str = "manual",
    source_id: str | None = None,
) -> dict[str, Any]:
    """Neo4j/本体感知的实体关系抽取。"""
    settings = get_settings()
    if not settings.kg_extraction_enabled or not is_configured():
        return {"skipped": True, "reason": "kg_extraction_disabled"}

    text = (text or "").strip()
    if len(text) < 50:
        return {"skipped": True, "reason": "text_too_short"}

    # 获取本体定义
    ontology = OntologyService(driver)
    entity_types = await ontology.list_entity_types()
    relation_types = await ontology.list_relation_types()

    entity_types_json = _format_entity_types_for_prompt(entity_types)
    relation_types_json = _format_relation_types_for_prompt(relation_types)

    # 调用 LLM 抽取
    system = EXTRACTION_SYSTEM_V2.format(
        entity_types_json=entity_types_json,
        relation_types_json=relation_types_json,
        max_entities=_MAX_ENTITIES,
        max_relations=_MAX_RELATIONS,
    )
    user_content = (
        f"文档标题：{title or '未命名'}\n\n"
        f"正文：\n{_clip_text(text, settings.kg_extraction_max_chars or 10000)}"
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
        return {"skipped": True, "reason": "llm_failed", "error": "模型未返回内容"}

    try:
        data = _extract_json(raw)
    except ValueError as exc:
        return {"skipped": True, "reason": "llm_failed", "error": str(exc)}

    entities_raw = _normalize_entities(data)
    relations_raw = _normalize_relations(data)

    if not entities_raw:
        return {
            "skipped": True,
            "reason": "llm_failed",
            "error": "未解析到有效实体",
        }

    # 后验证
    validation_errors = await _validate_extraction(driver, ontology, entities_raw, relations_raw)

    # 写入 Neo4j
    kg = KgService(driver)
    name_to_id: dict[str, str] = {}
    entities_created = 0
    relations_created = 0

    # 先创建实体（去重）
    for ent in entities_raw:
        existing = await _find_entity_by_name(driver, ent["name"], user_id)
        if existing:
            name_to_id[ent["name"]] = existing
        else:
            try:
                result = await kg.create_entity(
                    EntityIn(
                        type_code=ent["type_code"],
                        name=ent["name"],
                        description=ent.get("description", ""),
                        source_type="extraction",
                        source_document_id=source_id,
                    ),
                    user_id,
                )
                name_to_id[ent["name"]] = result.id
                entities_created += 1
            except ValueError as exc:
                logger.warning("实体抽取创建失败: %s", exc)

    # 再创建关系
    for rel in relations_raw:
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
            logger.debug("关系抽取创建跳过: %s", exc)

    return {
        "skipped": False,
        "entities_created": entities_created,
        "relations_created": relations_created,
        "validation_errors": validation_errors,
    }


async def _find_entity_by_name(driver: AsyncDriver, name: str, user_id: str) -> str | None:
    """按名称查找已有实体（使用 Neo4jBaseService 统一查询模式）。"""
    base = Neo4jBaseService(driver)
    records = await base.run_and_collect(
        "MATCH (e:Entity {name: $name, owner_id: $owner_id}) RETURN e.id AS id LIMIT 1",
        {"name": name.strip(), "owner_id": user_id},
    )
    if records:
        return records[0].get("id")
    return None


async def _validate_extraction(
    driver: AsyncDriver,
    ontology: OntologyService,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[str]:
    """验证抽取结果是否符合 ontology。"""
    errors: list[str] = []

    # 收集实体的 type_code
    entity_type_map: dict[str, str] = {}  # name -> type_code
    for ent in entities:
        entity_type_map[ent["name"]] = ent["type_code"]

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
                f"关系 '{rel['type_code']}' 的起点 '{rel['from_name']}' "
                f"类型 '{from_type}' 不在 domain {rt.domain_types} 中"
            )
        if rt.range_types and to_type not in rt.range_types:
            errors.append(
                f"关系 '{rel['type_code']}' 的终点 '{rel['to_name']}' "
                f"类型 '{to_type}' 不在 range {rt.range_types} 中"
            )

    return errors


def _format_entity_types_for_prompt(entity_types: list[Any]) -> str:
    buf = StringIO()
    for et in entity_types:
        required = [
            k for k, v in (et.property_schema or {}).items() if getattr(v, "required", False)
        ]
        req_str = f" [必需: {', '.join(required)}]" if required else ""
        buf.write(f"- {et.code} ({et.label}){req_str}\n")
    return buf.getvalue()


def _format_relation_types_for_prompt(relation_types: list[Any]) -> str:
    buf = StringIO()
    for rt in relation_types:
        domain = f" domain:{rt.domain_types}" if rt.domain_types else ""
        range_ = f" range:{rt.range_types}" if rt.range_types else ""
        buf.write(f"- {rt.code} ({rt.label}){domain}{range_}\n")
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


def _normalize_entities(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = data.get("entities", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:256]
        if not name or name in seen:
            continue
        type_code = str(item.get("type_code") or "doc").strip()
        description = str(item.get("description") or "").strip()[:1000]
        out.append({"type_code": type_code, "name": name, "description": description})
        seen.add(name)
        if len(out) >= _MAX_ENTITIES:
            break
    return out


def _normalize_relations(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = data.get("relations", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        from_name = str(item.get("from_name") or "").strip()
        to_name = str(item.get("to_name") or "").strip()
        if not from_name or not to_name or from_name == to_name:
            continue
        type_code = str(item.get("type_code") or "references").strip()
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
    return out
