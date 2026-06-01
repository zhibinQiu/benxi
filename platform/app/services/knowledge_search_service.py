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
    COMPANY_SCOPE_KEY,
    _get_registry,
    _visible_dataset_ids,
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

    candidates: list[str] = []

    def add_reg(reg_scope: str, key: str) -> None:
        reg = _get_registry(db, reg_scope, key)
        if reg and reg.ragflow_dataset_id:
            candidates.append(reg.ragflow_dataset_id)

    if scope is None or scope == SCOPE_COMPANY:
        if user_is_superuser(db, user) or user_has_permission(db, user, "doc.read"):
            add_reg(SCOPE_COMPANY, COMPANY_SCOPE_KEY)
    if scope is None or scope == SCOPE_DEPARTMENT:
        for dept_id in user_dept_ids(db, user.id):
            add_reg(SCOPE_DEPARTMENT, str(dept_id))
    if scope is None or scope == SCOPE_PERSONAL:
        add_reg(SCOPE_PERSONAL, str(user.id))

    try:
        visible = _visible_dataset_ids(kf)
        if visible:
            candidates = [ds for ds in candidates if ds in visible]
    except Exception as e:
        logger.warning("列举知识库失败，使用注册表缓存: %s", e)
    return list(dict.fromkeys(candidates))


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
