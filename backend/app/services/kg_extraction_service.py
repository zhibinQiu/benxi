"""索引完成后从文档正文 LLM 抽取实体/关系并写入知识图谱。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import user_has_permission
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.models.document import Document, DocumentVersion
from app.models.kg import KgEntity, KgEntityType, KgRelation, KgRelationType
from app.models.org import User
from app.services.compare_service import load_parsed_version
from app.services.kg.entity_commands import clear_user_graph
from app.services.kg.extraction_targets import (
    SCOPE_KNOWLEDGE,
    SCOPE_PLATFORM,
    collect_extraction_targets,
)
from app.services.kg_service import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    DOC_ENTITY_PROPERTY_KEY,
    ensure_doc_entity_for_document,
    ensure_ontology_defaults,
    find_entity_by_document_id,
)

logger = logging.getLogger(__name__)

EXTRACTED_VERSION_KEY = "kg_extracted_version_id"
EXTRACTED_AT_KEY = "kg_extracted_at"
SOURCE_DOCUMENT_KEY = "source_document_id"
SOURCE_VERSION_KEY = "source_version_id"
SOURCE_TYPE_KEY = "source_type"
SOURCE_ID_KEY = "source_id"
SOURCE_MEETING_SUMMARY = "meeting_summary"

_MAX_ENTITIES = 24
_MAX_RELATIONS = 32

_EXTRACTION_SYSTEM = """你是企业本体图谱抽取助手。根据文档正文识别关键实体与关系，输出严格 JSON。

实体类型 code 仅限：{entity_codes}
关系类型 code 仅限：{relation_codes}

输出格式（不要其它字段）：
{{
  "entities": [
    {{"type_code": "doc", "name": "实体名称", "description": "一句话说明"}}
  ],
  "relations": [
    {{"type_code": "references", "from_name": "起点实体名", "to_name": "终点实体名", "description": ""}}
  ]
}}

要求：
- 仅抽取正文中明确出现或可合理推断的实体，不要编造
- 实体名称简洁（≤40字），同一实体只出现一次
- 关系两端实体名必须与 entities 中 name 完全一致
- 最多 {max_entities} 个实体、{max_relations} 条关系
- 只输出 JSON，不要 Markdown 代码块"""


def kg_extraction_enabled() -> bool:
    settings = get_settings()
    return bool(settings.kg_extraction_enabled and is_configured())


def _user_may_extract(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.kg_palantir")


def _ontology_codes() -> tuple[str, str]:
    entity_codes = ", ".join(code for code, *_ in DEFAULT_ENTITY_TYPES)
    relation_codes = ", ".join(code for code, *_ in DEFAULT_RELATION_TYPES)
    return entity_codes, relation_codes


def extract_json_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
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


def _clip_document_text(text: str) -> str:
    limit = max(2000, int(get_settings().kg_extraction_max_chars or 10000))
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    head = body[: int(limit * 0.7)]
    tail = body[-int(limit * 0.25) :]
    return f"{head}\n\n…（中间省略）…\n\n{tail}"


def _call_llm_extract(*, document_title: str, text: str) -> dict[str, Any]:
    entity_codes, relation_codes = _ontology_codes()
    system = _EXTRACTION_SYSTEM.format(
        entity_codes=entity_codes,
        relation_codes=relation_codes,
        max_entities=_MAX_ENTITIES,
        max_relations=_MAX_RELATIONS,
    )
    user_content = (
        f"文档标题：{document_title or '未命名'}\n\n"
        f"正文：\n{_clip_document_text(text)}"
    )
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        timeout=120.0,
        max_user_chars=int(get_settings().kg_extraction_max_chars or 10000) + 500,
    )
    if not raw:
        raise ValueError("语言模型未返回抽取结果")
    data = extract_json_payload(raw)
    if not isinstance(data, dict):
        raise ValueError("抽取结果格式无效")
    return data


def _resolve_version(
    db: Session,
    doc: Document,
    version_id: uuid.UUID | None,
) -> DocumentVersion | None:
    if version_id:
        ver = db.get(DocumentVersion, version_id)
        if ver and ver.document_id == doc.id and ver.file_size > 0:
            return ver
    if doc.current_version_id:
        ver = db.get(DocumentVersion, doc.current_version_id)
        if ver and ver.file_size > 0:
            return ver
    return db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.file_size > 0,
        )
        .order_by(DocumentVersion.version_no.desc())
        .limit(1)
    )


def _already_extracted_for_version(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> bool:
    row = find_entity_by_document_id(db, user, document_id)
    if not row:
        return False
    props = row.properties or {}
    return str(props.get(EXTRACTED_VERSION_KEY) or "") == str(version_id)


def document_kg_extraction_status(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """文档本体抽离状态（按关联文档实体上的版本标记判断）。"""
    from app.services.document_service import get_document

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        return {"extracted": False, "reason": "document_not_found"}

    version = _resolve_version(db, doc, version_id) if doc else None
    if not version:
        return {"extracted": False, "reason": "no_uploaded_version"}

    row = find_entity_by_document_id(db, user, document_id)
    props = dict(row.properties or {}) if row else {}
    extracted_version_id = str(props.get(EXTRACTED_VERSION_KEY) or "") or None
    extracted_at = props.get(EXTRACTED_AT_KEY)
    extracted = extracted_version_id == str(version.id)
    return {
        "extracted": extracted,
        "document_id": str(document_id),
        "version_id": str(version.id),
        "extracted_version_id": extracted_version_id,
        "extracted_at": extracted_at,
        "needs_update": not extracted,
    }


def _type_maps(db: Session) -> tuple[dict[str, KgEntityType], dict[str, KgRelationType]]:
    ensure_ontology_defaults(db)
    entity_types = {
        t.code: t
        for t in db.scalars(select(KgEntityType)).all()
    }
    relation_types = {
        t.code: t
        for t in db.scalars(select(KgRelationType)).all()
    }
    return entity_types, relation_types


def _find_entity_by_name_and_type(
    db: Session,
    user: User,
    *,
    type_id: uuid.UUID,
    name: str,
) -> KgEntity | None:
    name = name.strip()[:256]
    if not name:
        return None
    return db.scalar(
        select(KgEntity).where(
            KgEntity.owner_id == user.id,
            KgEntity.type_id == type_id,
            KgEntity.name == name,
        )
    )


def _normalize_entity_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = data.get("entities")
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
        type_code = str(item.get("type_code") or "doc").strip() or "doc"
        description = str(item.get("description") or "").strip()[:1000]
        out.append(
            {
                "type_code": type_code,
                "name": name,
                "description": description,
            }
        )
        seen.add(name)
        if len(out) >= _MAX_ENTITIES:
            break
    return out


def _normalize_relation_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = data.get("relations")
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
        type_code = str(item.get("type_code") or "references").strip() or "references"
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


def _find_entity_by_source(
    db: Session,
    user: User,
    *,
    source_type: str,
    source_id: uuid.UUID | None,
) -> KgEntity | None:
    for row in db.scalars(select(KgEntity).where(KgEntity.owner_id == user.id)).all():
        props = row.properties or {}
        if str(props.get(SOURCE_TYPE_KEY) or "") != source_type:
            continue
        if source_id is None:
            return row
        if str(props.get(SOURCE_ID_KEY) or "") == str(source_id):
            return row
    return None


def _ensure_source_root_entity(
    db: Session,
    user: User,
    *,
    title: str,
    source_type: str,
    source_id: uuid.UUID | None,
) -> KgEntity:
    existing = _find_entity_by_source(
        db, user, source_type=source_type, source_id=source_id
    )
    if existing:
        return existing

    ensure_ontology_defaults(db)
    et = db.scalar(select(KgEntityType).where(KgEntityType.code == "project"))
    if not et:
        et = db.scalar(select(KgEntityType).where(KgEntityType.code == "doc"))
    if not et:
        raise ValueError("本体默认实体类型缺失")

    name = (title or "会议总结").strip()[:256] or "会议总结"
    props: dict[str, str] = {SOURCE_TYPE_KEY: source_type}
    if source_id:
        props[SOURCE_ID_KEY] = str(source_id)

    row = KgEntity(
        type_id=et.id,
        name=name,
        description=f"来自会议总结：{name}",
        properties=props,
        owner_id=user.id,
        created_by=user.id,
        scope="personal",
    )
    db.add(row)
    db.flush()
    return row


def _merge_extraction_data(
    db: Session,
    user: User,
    data: dict[str, Any],
    *,
    source_props: dict[str, str],
    seed_entities: dict[str, uuid.UUID] | None = None,
) -> dict[str, int]:
    """将 LLM 抽取的实体/关系合并写入用户图谱（幂等）。"""
    entity_types, relation_types = _type_maps(db)
    name_to_id: dict[str, uuid.UUID] = dict(seed_entities or {})

    created_entities = 0
    reused_entities = 0
    for item in _normalize_entity_rows(data):
        et = entity_types.get(item["type_code"]) or entity_types.get("doc")
        if not et:
            continue
        existing = _find_entity_by_name_and_type(
            db, user, type_id=et.id, name=item["name"]
        )
        if existing:
            name_to_id[item["name"]] = existing.id
            reused_entities += 1
            continue
        row = KgEntity(
            type_id=et.id,
            name=item["name"],
            description=item["description"],
            properties=dict(source_props),
            owner_id=user.id,
            created_by=user.id,
            scope="personal",
        )
        db.add(row)
        db.flush()
        name_to_id[item["name"]] = row.id
        created_entities += 1

    created_relations = 0
    skipped_relations = 0
    for item in _normalize_relation_rows(data):
        rt = relation_types.get(item["type_code"]) or relation_types.get("references")
        if not rt:
            continue
        from_id = name_to_id.get(item["from_name"])
        to_id = name_to_id.get(item["to_name"])
        if not from_id or not to_id or from_id == to_id:
            skipped_relations += 1
            continue
        dup = db.scalar(
            select(KgRelation).where(
                KgRelation.owner_id == user.id,
                KgRelation.relation_type_id == rt.id,
                KgRelation.from_entity_id == from_id,
                KgRelation.to_entity_id == to_id,
            )
        )
        if dup:
            skipped_relations += 1
            continue
        db.add(
            KgRelation(
                relation_type_id=rt.id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                description=item["description"],
                owner_id=user.id,
                created_by=user.id,
            )
        )
        created_relations += 1

    return {
        "entities_created": created_entities,
        "entities_reused": reused_entities,
        "relations_created": created_relations,
        "relations_skipped": skipped_relations,
    }


def apply_extraction_result(
    db: Session,
    user: User,
    doc: Document,
    version: DocumentVersion,
    data: dict[str, Any],
) -> dict[str, int]:
    """将 LLM 抽取结果写入用户图谱（幂等合并）。"""
    ensure_doc_entity_for_document(db, user, doc.id, commit=False)
    doc_row = find_entity_by_document_id(db, user, doc.id)

    seed_entities: dict[str, uuid.UUID] = {}
    if doc_row:
        seed_entities[doc_row.name] = doc_row.id

    source_props = {
        SOURCE_DOCUMENT_KEY: str(doc.id),
        SOURCE_VERSION_KEY: str(version.id),
    }
    stats = _merge_extraction_data(
        db,
        user,
        data,
        source_props=source_props,
        seed_entities=seed_entities,
    )

    if doc_row:
        props = dict(doc_row.properties or {})
        props[DOC_ENTITY_PROPERTY_KEY] = str(doc.id)
        props[EXTRACTED_VERSION_KEY] = str(version.id)
        props[EXTRACTED_AT_KEY] = datetime.now(timezone.utc).isoformat()
        doc_row.properties = props

    db.flush()
    return stats


def apply_extraction_result_from_text(
    db: Session,
    user: User,
    *,
    title: str,
    data: dict[str, Any],
    source_type: str = SOURCE_MEETING_SUMMARY,
    source_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """将 LLM 抽取结果写入用户图谱，并以会议/文本来源登记根实体。"""
    root = _ensure_source_root_entity(
        db,
        user,
        title=title,
        source_type=source_type,
        source_id=source_id,
    )
    source_props: dict[str, str] = {SOURCE_TYPE_KEY: source_type}
    if source_id:
        source_props[SOURCE_ID_KEY] = str(source_id)

    stats = _merge_extraction_data(
        db,
        user,
        data,
        source_props=source_props,
        seed_entities={root.name: root.id},
    )

    props = dict(root.properties or {})
    props.update(source_props)
    props[EXTRACTED_AT_KEY] = datetime.now(timezone.utc).isoformat()
    root.properties = props
    db.flush()
    return {**stats, "root_entity_id": str(root.id)}


def extract_kg_from_text(
    db: Session,
    user: User,
    *,
    title: str,
    text: str,
    source_type: str = SOURCE_MEETING_SUMMARY,
    source_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """从任意文本（如会议总结）抽取实体/关系并写入图谱。"""
    if not kg_extraction_enabled():
        return {"skipped": True, "reason": "kg_extraction_disabled"}
    if not _user_may_extract(db, user):
        return {"skipped": True, "reason": "no_kg_permission"}

    body = (text or "").strip()
    if len(body) < 40:
        return {"skipped": True, "reason": "text_too_short"}

    try:
        llm_data = _call_llm_extract(
            document_title=title or "会议总结",
            text=body,
        )
    except Exception as exc:
        logger.warning("KG 文本抽取 LLM 失败: %s", exc)
        return {"skipped": True, "reason": "llm_failed", "error": str(exc)[:200]}

    stats = apply_extraction_result_from_text(
        db,
        user,
        title=title or "会议总结",
        data=llm_data,
        source_type=source_type,
        source_id=source_id,
    )
    db.commit()
    from app.core.platform_cache import invalidate_kg_cache

    invalidate_kg_cache(user.id)
    return {"skipped": False, **stats}


def extract_kg_from_document(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """从已索引文档正文抽取实体/关系并写入图谱。"""
    if not kg_extraction_enabled():
        return {"skipped": True, "reason": "kg_extraction_disabled"}
    if not _user_may_extract(db, user):
        return {"skipped": True, "reason": "no_kg_permission"}

    from app.services.document_service import get_document

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        return {"skipped": True, "reason": "document_not_found"}

    version = _resolve_version(db, doc, version_id)
    if not version:
        return {"skipped": True, "reason": "no_uploaded_version"}

    if not force and _already_extracted_for_version(db, user, doc.id, version.id):
        return {"skipped": True, "reason": "already_extracted", "version_id": str(version.id)}

    try:
        parsed = load_parsed_version(db, version)
    except Exception as exc:
        logger.warning("KG 抽取读取正文失败 doc=%s: %s", document_id, exc)
        return {"skipped": True, "reason": "text_load_failed"}

    text = (parsed.full_text or "").strip()
    if len(text) < 80:
        return {"skipped": True, "reason": "text_too_short"}

    try:
        llm_data = _call_llm_extract(
            document_title=doc.title or parsed.file_name,
            text=text,
        )
    except Exception as exc:
        logger.warning("KG 抽取 LLM 失败 doc=%s: %s", document_id, exc)
        return {"skipped": True, "reason": "llm_failed", "error": str(exc)[:200]}

    stats = apply_extraction_result(db, user, doc, version, llm_data)
    db.commit()
    from app.core.platform_cache import invalidate_kg_cache

    invalidate_kg_cache(user.id)
    return {
        "skipped": False,
        "document_id": str(document_id),
        "version_id": str(version.id),
        **stats,
    }


def _run_kg_extraction_job(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID | None,
) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return
        result = extract_kg_from_document(
            db,
            user,
            document_id,
            version_id=version_id,
        )
        if not result.get("skipped"):
            logger.info(
                "KG 文档抽取完成 doc=%s entities=%s relations=%s",
                document_id,
                result.get("entities_created"),
                result.get("relations_created"),
            )
    except Exception:
        logger.exception("KG 文档抽取后台任务失败 doc=%s", document_id)
        db.rollback()
    finally:
        db.close()


def schedule_kg_extraction_after_index(
    *,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> None:
    """单文档图谱抽取（供手动触发或兼容调用）。"""
    if not kg_extraction_enabled():
        return
    from app.core.background_executor import submit_background

    submit_background(
        f"kg-extract-{document_id}",
        _run_kg_extraction_job,
        document_id,
        user_id,
        version_id,
    )


_SCOPE_LABELS = {
    SCOPE_KNOWLEDGE: "知识库",
    SCOPE_PLATFORM: "平台库",
}


def _run_kg_batch_extraction_job(
    user_id: uuid.UUID,
    scope: str,
    *,
    force: bool,
) -> None:
    from app.database import SessionLocal
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return
        effective_force = force
        if scope == SCOPE_KNOWLEDGE:
            clear_user_graph(db, user)
            effective_force = True
        plan = collect_extraction_targets(db, user, scope=scope, force=effective_force)
        if not plan.pending:
            return
        processed = 0
        succeeded = 0
        skipped = 0
        for doc_id, version_id in plan.pending:
            try:
                result = extract_kg_from_document(
                    db,
                    user,
                    doc_id,
                    version_id=version_id,
                    force=force,
                )
            except Exception:
                logger.exception(
                    "KG 批量抽离单文档失败 doc=%s scope=%s", doc_id, scope
                )
                db.rollback()
                processed += 1
                skipped += 1
                continue
            processed += 1
            if result.get("skipped"):
                skipped += 1
            else:
                succeeded += 1

        label = _SCOPE_LABELS.get(scope, scope)
        create_notification(
            db,
            user_id=user.id,
            title="本体图谱抽离完成",
            body=(
                f"{label}增量抽离已结束：待处理 {processed} 份，"
                f"成功 {succeeded} 份，跳过 {skipped} 份"
                f"（已有标记 {plan.already_extracted_count} 份未重复处理）。"
                "可在本体图谱中查看更新结果。"
            ),
            link="/kg-palantir",
        )
        db.commit()
        logger.info(
            "KG 批量抽离完成 scope=%s user=%s processed=%s succeeded=%s skipped=%s",
            scope,
            user_id,
            processed,
            succeeded,
            skipped,
        )
    except Exception:
        logger.exception("KG 批量抽离失败 scope=%s user=%s", scope, user_id)
        db.rollback()
    finally:
        db.close()


def schedule_kg_batch_extraction(
    db: Session,
    user: User,
    *,
    scope: str,
    force: bool = False,
) -> dict[str, Any]:
    """在本体图谱页手动触发批量抽离（后台异步执行，默认增量跳过已标记文档）。"""
    if not kg_extraction_enabled():
        return {"queued": False, "reason": "kg_extraction_disabled", "scope": scope}
    if not _user_may_extract(db, user):
        return {"queued": False, "reason": "no_kg_permission", "scope": scope}
    if scope not in (SCOPE_KNOWLEDGE, SCOPE_PLATFORM):
        return {"queued": False, "reason": "invalid_scope", "scope": scope}

    plan = collect_extraction_targets(db, user, scope=scope, force=force)
    if plan.total_candidates == 0:
        return {
            "queued": False,
            "reason": "no_documents",
            "scope": scope,
            "document_count": 0,
            "already_extracted_count": 0,
            "total_candidates": 0,
        }
    if not plan.pending:
        return {
            "queued": False,
            "reason": "all_extracted",
            "scope": scope,
            "document_count": 0,
            "already_extracted_count": plan.already_extracted_count,
            "total_candidates": plan.total_candidates,
        }

    from app.core.background_executor import submit_background

    submit_background(
        f"kg-batch-extract-{user.id}-{scope}",
        _run_kg_batch_extraction_job,
        user.id,
        scope,
        force=force,
    )
    return {
        "queued": True,
        "scope": scope,
        "document_count": len(plan.pending),
        "already_extracted_count": plan.already_extracted_count,
        "total_candidates": plan.total_candidates,
    }
