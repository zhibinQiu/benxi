"""平台原生知识搜索：调用 KnowFlow/RAGFlow 检索 API，不嵌入 KnowFlow 前端。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_TEAM,
    SCOPE_PERSONAL,
    VALID_SCOPES,
    can_query_document,
)
from app.core.exceptions import bad_request
from app.core.permissions import user_dept_ids, user_has_permission, user_is_superuser
from app.integrations.knowflow_client import get_knowflow_client_for_user, knowflow_stack_reachable
from app.integrations.text_extract import local_search
from app.models.document import Document
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.services.compare_service import load_parsed_documents
from app.services.document_service import get_document, list_queryable_documents
from app.services.ragflow_scope_service import (
    allowed_dataset_ids_for_user,
    visible_dataset_ids_for_user,
)
from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
    SCOPE_TEAM as REG_TEAM,
    SCOPE_PERSONAL as REG_PERSONAL,
    RagflowScopeDataset,
)

logger = logging.getLogger(__name__)


def _dataset_ids_for_search(
    db: Session,
    user: User,
    kf,
    *,
    scope: str | None,
) -> list[str]:
    if scope and scope not in VALID_SCOPES:
        raise bad_request("无效的分级 scope")
    if not hasattr(kf, "_rag"):
        return []

    from app.core.document_scope import scope_for_department

    allowed = allowed_dataset_ids_for_user(db, user)
    visible = visible_dataset_ids_for_user(db, user, kf)
    if visible:
        allowed = allowed & visible

    if not scope:
        return list(dict.fromkeys(allowed))

    filtered: list[str] = []
    for ds_id in allowed:
        reg = db.scalar(
            select(RagflowScopeDataset).where(
                RagflowScopeDataset.ragflow_dataset_id == ds_id
            )
        )
        if not reg:
            continue
        if scope == SCOPE_PERSONAL:
            if reg.scope == REG_PERSONAL and reg.scope_key == str(user.id):
                filtered.append(ds_id)
        elif scope == SCOPE_COMPANY:
            if reg.scope == REG_COMPANY:
                filtered.append(ds_id)
        elif scope in (SCOPE_DEPARTMENT, SCOPE_TEAM):
            if reg.scope not in (REG_DEPARTMENT, REG_TEAM):
                continue
            try:
                dept_uuid = uuid.UUID(reg.scope_key)
            except ValueError:
                continue
            if scope_for_department(db, dept_uuid) == scope:
                filtered.append(ds_id)
    return list(dict.fromkeys(filtered))


def _safe_score(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_anchor(value) -> dict | None:
    return value if isinstance(value, dict) else None


def _hit_row(
    *,
    document_id: str,
    title: str | None,
    scope: str | None,
    snippet: str | None,
    score,
    source: str,
    anchor_json,
) -> dict:
    return {
        "document_id": document_id,
        "title": (title or "").strip() or "未命名文档",
        "scope": scope or SCOPE_PERSONAL,
        "snippet": ((snippet or "")[:2000]),
        "score": _safe_score(score),
        "source": source,
        "anchor_json": _safe_anchor(anchor_json),
    }


def _ragflow_to_platform_map(
    db: Session, ragflow_doc_ids: list[str]
) -> dict[str, uuid.UUID]:
    if not ragflow_doc_ids:
        return {}
    rows = list(
        db.scalars(
            select(RagflowDocumentLink).where(
                RagflowDocumentLink.ragflow_document_id.in_(ragflow_doc_ids)
            )
        ).all()
    )
    return {r.ragflow_document_id: r.platform_document_id for r in rows}


def _enrich_hits(
    db: Session,
    user: User,
    raw_hits: list[dict],
    *,
    limit: int,
) -> list[dict]:
    rag_ids = [
        str(h.get("ragflow_document_id") or h.get("document_id") or "")
        for h in raw_hits
    ]
    rag_ids = [x for x in rag_ids if x]
    id_map = _ragflow_to_platform_map(db, rag_ids)

    out: list[dict] = []
    seen_docs: set[str] = set()
    for h in raw_hits:
        rid = str(h.get("ragflow_document_id") or h.get("document_id") or "")
        pid = id_map.get(rid)
        if pid is None and h.get("document_id"):
            try:
                pid = uuid.UUID(str(h["document_id"]))
            except ValueError:
                pid = None
        if pid is None:
            continue
        pid_str = str(pid)
        doc = get_document(db, pid)
        if not doc or not can_query_document(db, user, doc):
            continue
        if pid_str in seen_docs and len(out) >= limit:
            continue
        seen_docs.add(pid_str)
        out.append(
            _hit_row(
                document_id=pid_str,
                title=doc.title,
                scope=doc.scope,
                snippet=h.get("snippet"),
                score=h.get("score"),
                source=h.get("source", "knowflow"),
                anchor_json=h.get("anchor_json"),
            )
        )
        if len(out) >= limit:
            break
    return out


def _local_search_fallback(
    db: Session,
    user: User,
    query: str,
    *,
    scope: str | None,
    limit: int,
) -> list[dict]:
    docs, _ = list_queryable_documents(
        db, user, page=1, page_size=min(limit * 3, 60), keyword=None
    )
    if scope:
        docs = [d for d in docs if (d.scope or SCOPE_PERSONAL) == scope]
    if not docs:
        return []
    try:
        parsed = load_parsed_documents(db, docs)
    except Exception:
        return []
    scope_ids = [str(d.id) for d in docs]
    hits = local_search(
        [p for p in parsed if str(p.document_id) in scope_ids],
        query,
        limit=limit,
    )
    out: list[dict] = []
    for h in hits:
        pid = str(h.get("document_id", ""))
        doc = get_document(db, uuid.UUID(pid)) if pid else None
        if not doc:
            continue
        out.append(
            _hit_row(
                document_id=pid,
                title=doc.title,
                scope=doc.scope,
                snippet=h.get("snippet"),
                score=h.get("score"),
                source="local",
                anchor_json=h.get("anchor_json"),
            )
        )
    return out


def search_knowledge(
    db: Session,
    user: User,
    *,
    query: str,
    scope: str | None = None,
    limit: int = 20,
) -> dict:
    q = (query or "").strip()
    if not q:
        raise bad_request("请输入搜索关键词")
    limit = max(1, min(limit, 50))

    settings = get_settings()
    stack_on = settings.knowflow_enabled and knowflow_stack_reachable()
    kf = get_knowflow_client_for_user(db, user)
    hits: list[dict] = []
    mode = "local"

    if stack_on and kf.enabled():
        try:
            dataset_ids = _dataset_ids_for_search(db, user, kf, scope=scope)
            if dataset_ids and hasattr(kf, "_rag"):
                raw = kf._rag.retrieval(
                    question=q,
                    dataset_ids=dataset_ids,
                    top_k=limit * 2,
                )
                for h in raw:
                    h.setdefault("source", "knowflow")
                hits = _enrich_hits(db, user, raw, limit=limit)
                if hits:
                    mode = "knowflow"
        except Exception as e:
            logger.warning("KnowFlow 检索失败，回退本地: %s", e)
            hits = []

    if not hits:
        hits = _local_search_fallback(db, user, q, scope=scope, limit=limit)
        mode = "local"

    return {
        "query": q,
        "hits": hits,
        "knowflow_enabled": stack_on,
        "search_mode": mode,
    }
