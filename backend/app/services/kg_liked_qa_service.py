"""用户点赞的问答摘要写入知识图谱，供后续关键词命中直答。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from typing import Any

_logger = logging.getLogger(__name__)

LIKED_QA_PROP = "liked_qa_hash"
_MAX_NAME = 120
_MAX_DESC = 2000


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _question_hash(question: str) -> str:
    return hashlib.sha256(_normalize_question(question).encode("utf-8")).hexdigest()[:32]


def _summarize_question(question: str) -> str:
    q = _normalize_question(question)
    if len(q) <= _MAX_NAME:
        return q
    return q[: _MAX_NAME - 1] + "…"


def _summarize_answer(answer: str) -> str:
    a = (answer or "").strip()
    if len(a) <= _MAX_DESC:
        return a
    return a[: _MAX_DESC - 1] + "…"


def invalidate_kg_decision_cache_for_user(user_id: str) -> None:
    """点赞写入后清掉该用户规划侧图谱短时缓存。"""
    try:
        from app.services.agent_planner import _KG_DECISION_CACHE

        prefix = f"{user_id}::"
        dead = [k for k in list(_KG_DECISION_CACHE.keys()) if str(k).startswith(prefix)]
        for k in dead:
            _KG_DECISION_CACHE.pop(k, None)
    except Exception:
        _logger.debug("clear kg decision cache failed", exc_info=True)


async def upsert_liked_qa_to_kg(
    *,
    user_id: str,
    question: str,
    answer: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """将点赞问答以 memory 实体 upsert 到当前用户图谱。

    entity.name = 问题摘要（供 match_entities_in_question 关键词命中）
    entity.description = 答案摘要（供直答引用）
    """
    from app.core.neo4j import get_neo4j
    from app.services.kg_service import KgService

    q = _normalize_question(question)
    a = (answer or "").strip()
    if not q or not a:
        return {"ok": False, "error": "question_and_answer_required"}

    q_hash = _question_hash(q)
    name = _summarize_question(q)
    desc = _summarize_answer(a)
    props = {
        LIKED_QA_PROP: q_hash,
        "source": "user_liked",
        "question": q[:800],
        "conversation_id": (conversation_id or "").strip() or None,
    }
    props = {k: v for k, v in props.items() if v is not None}
    props_json = json.dumps(props, ensure_ascii=False)
    owner = str(user_id)

    driver = await get_neo4j()
    kg = KgService(driver)
    existing = await kg.run_single(
        f"""
        MATCH (e:Entity {{owner_id: $owner}})
        WHERE e.{LIKED_QA_PROP} = $h
        RETURN e LIMIT 1
        """,
        {"owner": owner, "h": q_hash},
    )
    if existing:
        node = dict(existing["e"])
        eid = str(node.get("id") or "")
        await kg.run_single(
            f"""
            MATCH (e:Entity {{id: $id}})
            SET e.name = $name,
                e.description = $desc,
                e.type_code = 'memory',
                e.source_type = 'manual',
                e.updated_at = datetime(),
                e.{LIKED_QA_PROP} = $h,
                e.properties = $props
            RETURN e.id AS id
            """,
            {
                "id": eid,
                "name": name,
                "desc": desc,
                "h": q_hash,
                "props": props_json,
            },
        )
        invalidate_kg_decision_cache_for_user(owner)
        return {"ok": True, "entity_id": eid, "created": False, "name": name}

    eid = str(uuid.uuid4())
    await kg.run_single(
        f"""
        CREATE (e:Entity {{
            id: $id,
            type_code: 'memory',
            name: $name,
            description: $desc,
            properties: $props,
            source_type: 'manual',
            owner_id: $owner,
            created_by: $owner,
            {LIKED_QA_PROP}: $h,
            created_at: datetime(),
            updated_at: datetime()
        }})
        RETURN e.id AS id
        """,
        {
            "id": eid,
            "name": name,
            "desc": desc,
            "props": props_json,
            "owner": owner,
            "h": q_hash,
        },
    )
    invalidate_kg_decision_cache_for_user(owner)
    return {"ok": True, "entity_id": eid, "created": True, "name": name}
