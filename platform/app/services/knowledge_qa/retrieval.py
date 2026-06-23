"""Knowledge QA — 混合检索."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import PermissionLevel
from app.domains.knowledge import knowledge
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.integrations.text_extract import local_search
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.document_service import get_document, resolve_current_version
from app.services.ragflow_version_link_service import (
    ragflow_to_platform_version_map,
    resolve_index_link,
    resolve_latest_indexed_version,
)

logger = logging.getLogger(__name__)

_RETRIEVAL_QUERY_MAX_WORKERS = 4
_RETRIEVAL_ENGINE_MAX_WORKERS = 2


def _qa_db_pool_budget() -> int:
    """为常规 API 保留连接池，限制 QA 并行占用的 DB session 数。"""
    settings = get_settings()
    pool = max(
        1,
        int(settings.db_pool_size or 15) + int(settings.db_max_overflow or 15),
    )
    return max(1, pool // 4)


def _qa_retrieval_max_workers(requested: int | None = None) -> int:
    cap = min(_RETRIEVAL_QUERY_MAX_WORKERS, _qa_db_pool_budget())
    if requested is None:
        return cap
    return max(1, min(int(requested), cap))


def _qa_engine_max_workers() -> int:
    return min(_RETRIEVAL_ENGINE_MAX_WORKERS, max(1, _qa_db_pool_budget() // 2))


def _rag_clients_for_qa(db: Session, user: User) -> list[RagflowClient]:
    from app.services.model_settings_service import get_ragflow_api_key
    from app.services.ragflow_identity_service import get_user_ragflow_auth
    from app.services.ragflow_scope_service import _privileged_rag_client

    clients: list[RagflowClient] = []
    seen: set[str] = set()

    def _add(client: RagflowClient | None) -> None:
        if client is None:
            return
        key = (client.session_auth or "") + "|" + (client.api_key or "")
        if key in seen:
            return
        seen.add(key)
        clients.append(client)

    # 用户 KnowFlow 客户端优先，减少无效 fallback 探活
    kf = knowledge.client_for_user(db, user)
    if hasattr(kf, "_rag"):
        _add(kf._rag)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        _add(RagflowClient(session_auth=auth))
    api_key = (get_ragflow_api_key(db) or "").strip()
    if api_key:
        _add(RagflowClient(api_key=api_key))
    priv = _privileged_rag_client(db)
    _add(priv)
    settings = get_settings()
    if settings.ragflow_api_key and settings.ragflow_api_key != api_key:
        _add(RagflowClient(api_key=settings.ragflow_api_key))
    return clients


def _resolve_hit_platform_document_id(
    h: dict,
    allowed: set[str],
    vmap: dict[str, dict],
) -> str | None:
    """将检索命中映射为平台 document_id（RAGFlow 切片常只有 ragflow_document_id）。"""
    rid = str(h.get("ragflow_document_id") or "")
    did_raw = h.get("document_id")
    if did_raw:
        try:
            did_str = str(uuid.UUID(str(did_raw)))
            if did_str in allowed:
                return did_str
        except ValueError:
            pass
    if rid and rid in vmap:
        pid = vmap[rid].get("platform_document_id")
        if pid and pid in allowed:
            return pid
    return None


def _filter_hits_by_version(
    db: Session,
    user: User,
    hits: list[dict],
    doc_ids: list[uuid.UUID],
) -> list[dict]:
    allowed = {str(d) for d in doc_ids}
    rag_ids = [
        str(h.get("ragflow_document_id") or h.get("document_id") or "") for h in hits
    ]
    vmap = ragflow_to_platform_version_map(db, [x for x in rag_ids if x])
    platform_ids: set[str] = set()
    for h in hits:
        pid = _resolve_hit_platform_document_id(h, allowed, vmap)
        if pid:
            platform_ids.add(pid)
    docs_by_id: dict[str, Document] = {}
    if platform_ids:
        for doc in db.scalars(
            select(Document).where(
                Document.id.in_([uuid.UUID(x) for x in platform_ids])
            )
        ).all():
            docs_by_id[str(doc.id)] = doc
    version_by_doc: dict[str, DocumentVersion | None] = {}
    indexed_rag_id_by_doc: dict[str, str] = {}
    if docs_by_id:
        from app.services.document_index_service import _batch_version_links_by_document

        doc_uuid_list = [doc.id for doc in docs_by_id.values()]
        version_links_by_doc = _batch_version_links_by_document(db, doc_uuid_list)
        for pid, doc in docs_by_id.items():
            links = version_links_by_doc.get(pid, [])
            indexed = resolve_latest_indexed_version(db, doc, version_links=links)
            version_by_doc[pid] = indexed or resolve_current_version(db, doc)
            for link in links:
                if link.index_completed_at and (link.ragflow_document_id or "").strip():
                    indexed_rag_id_by_doc[pid] = str(link.ragflow_document_id).strip()
                    break
            if pid not in indexed_rag_id_by_doc:
                for link in links:
                    if link.ragflow_document_id and link.dataset_id:
                        indexed_rag_id_by_doc[pid] = str(link.ragflow_document_id).strip()
                        break

    filtered: list[dict] = []
    for h in hits:
        rid = str(h.get("ragflow_document_id") or "")
        platform_id = _resolve_hit_platform_document_id(h, allowed, vmap)
        if not platform_id or platform_id not in docs_by_id:
            continue
        current = version_by_doc.get(platform_id)
        chunk_ver = (vmap.get(rid) or {}).get("document_version_id")
        indexed_rid = indexed_rag_id_by_doc.get(platform_id, "")
        if indexed_rid and rid and rid == indexed_rid:
            pass
        elif current and chunk_ver and chunk_ver != str(current.id):
            continue
        normalized = dict(h)
        normalized["document_id"] = platform_id
        filtered.append(normalized)
    return filtered


def _knowflow_retrieval_available(db: Session, user: User) -> bool:
    from app.integrations.ragflow_http import should_attempt_ragflow_http

    if not get_settings().knowflow_enabled:
        return False
    if not should_attempt_ragflow_http():
        return False
    return bool(_rag_clients_for_qa(db, user))


def _resolve_dataset_ids_for_ragflow_docs(
    db: Session, rag_doc_ids: list[str]
) -> list[str]:
    """按 RAGFlow 文档 ID 从索引链接表补全 dataset_id。"""
    ids = [str(x).strip() for x in rag_doc_ids if str(x).strip()]
    if not ids:
        return []
    dataset_ids: list[str] = []
    for row in db.scalars(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.ragflow_document_id.in_(ids)
        )
    ).all():
        ds = (row.dataset_id or "").strip()
        if ds:
            dataset_ids.append(ds)
    for row in db.scalars(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.ragflow_document_id.in_(ids)
        )
    ).all():
        ds = (row.dataset_id or "").strip()
        if ds:
            dataset_ids.append(ds)
    return list(dict.fromkeys(dataset_ids))


def _qa_retrieval_targets(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    *,
    docs_by_id: dict[str, Document] | None = None,
) -> tuple[list[str], list[str]]:
    """按最后索引成功版本收集 RAG 检索目标（复用文档对比/同步映射）。"""
    from app.models.ragflow_document_link import RagflowDocumentLink
    from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
    from app.services.document_index_service import _batch_version_links_by_document
    from app.services.ragflow_sync_service import (
        allowed_ragflow_doc_map,
    )

    platform_ids = [str(d) for d in doc_ids]
    ragflow_map = allowed_ragflow_doc_map(db, user, platform_ids)
    if docs_by_id is None:
        docs_by_id = {}
    missing = [
        uuid.UUID(pid)
        for pid in platform_ids
        if pid not in docs_by_id and pid in ragflow_map
    ]
    if missing:
        for doc in db.scalars(select(Document).where(Document.id.in_(missing))).all():
            docs_by_id[str(doc.id)] = doc

    doc_uuid_list = [uuid.UUID(pid) for pid in platform_ids if pid in docs_by_id]
    mirrors: dict[uuid.UUID, RagflowDocumentMirrorLink] = {}
    if doc_uuid_list:
        for row in db.scalars(
            select(RagflowDocumentMirrorLink).where(
                RagflowDocumentMirrorLink.platform_document_id.in_(doc_uuid_list),
                RagflowDocumentMirrorLink.platform_user_id == user.id,
            )
        ).all():
            mirrors[row.platform_document_id] = row

    canon: dict[uuid.UUID, RagflowDocumentLink] = {}
    if doc_uuid_list:
        for row in db.scalars(
            select(RagflowDocumentLink).where(
                RagflowDocumentLink.platform_document_id.in_(doc_uuid_list)
            )
        ).all():
            canon[row.platform_document_id] = row

    version_links_by_doc = _batch_version_links_by_document(db, doc_uuid_list)

    dataset_ids: list[str] = []
    rag_doc_ids: list[str] = []

    for pid in platform_ids:
        rag_id = ragflow_map.get(pid)
        if not rag_id:
            continue
        rag_doc_ids.append(str(rag_id).strip())
        try:
            doc_uuid = uuid.UUID(pid)
        except ValueError:
            continue
        doc = docs_by_id.get(pid)
        if not doc:
            continue
        ds_id: str | None = None
        mirror = mirrors.get(doc_uuid)
        if mirror and mirror.dataset_id:
            ds_id = str(mirror.dataset_id).strip()
        if not ds_id:
            for link in version_links_by_doc.get(pid, []):
                if link.index_completed_at and link.dataset_id:
                    ds_id = str(link.dataset_id).strip()
                    break
        if not ds_id:
            for link in version_links_by_doc.get(pid, []):
                if link.dataset_id:
                    ds_id = str(link.dataset_id).strip()
                    break
        if not ds_id:
            link = canon.get(doc_uuid)
            if link and link.dataset_id:
                ds_id = str(link.dataset_id).strip()
        if ds_id:
            dataset_ids.append(ds_id)

    return list(dict.fromkeys(dataset_ids)), list(dict.fromkeys(rag_doc_ids))


def _knowflow_retrieve(
    db: Session,
    user: User,
    docs,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    from app.integrations.ragflow_http import should_attempt_ragflow_http

    dataset_ids, rag_doc_ids = _qa_retrieval_targets(
        db,
        user,
        doc_ids,
        docs_by_id={str(d.id): d for d in docs},
    )
    if not rag_doc_ids:
        return []
    if not dataset_ids:
        dataset_ids = _resolve_dataset_ids_for_ragflow_docs(db, rag_doc_ids)
    if not dataset_ids:
        return []

    settings = get_settings()
    top_k = max(1, min(int(limit), 20))
    threshold = float(settings.knowledge_retrieval_similarity_threshold or 0.32)
    if not should_attempt_ragflow_http():
        return []

    payload_kwargs = {
        "question": question,
        "dataset_ids": dataset_ids,
        "document_ids": rag_doc_ids or None,
        "top_k": top_k,
        "keyword": True,
        "highlight": True,
        "vector_similarity_weight": float(settings.knowledge_retrieval_vector_weight),
        "similarity_threshold": threshold,
    }
    for rag in _rag_clients_for_qa(db, user):
        try:
            raw = rag.retrieval(**payload_kwargs)
            hits = _filter_hits_by_version(db, user, raw, doc_ids)
            if hits:
                return hits[:top_k]
        except RagflowError as exc:
            logger.debug("知识检索 KnowFlow 检索失败: %s", exc)
    return []


def _local_retrieve(
    db: Session,
    user: User,
    docs,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    from app.services.compare_service import load_parsed_documents

    try:
        parsed = load_parsed_documents(db, docs)
    except Exception:
        return []
    scope_ids = [str(d.id) for d in docs]
    hits = local_search(
        [p for p in parsed if str(p.document_id) in scope_ids],
        question,
        limit=limit,
    )
    out: list[dict] = []
    for h in hits:
        pid = str(h.get("document_id", ""))
        if pid not in scope_ids:
            continue
        doc = get_document(db, uuid.UUID(pid))
        if not doc:
            continue
        out.append(
            {
                "document_id": pid,
                "snippet": h.get("snippet") or "",
                "highlight": h.get("snippet") or "",
                "score": h.get("score"),
                "anchor_json": h.get("anchor_json"),
                "preview_available": False,
                "source": "local",
            }
        )
    return out[:limit]


def _merge_hits_by_score(hits: list[dict], *, limit: int) -> list[dict]:
    if not hits or limit <= 0:
        return []
    best: dict[tuple, dict] = {}
    order: list[tuple] = []
    for h in hits:
        did = str(h.get("document_id") or "")
        chunk = str(h.get("chunk_id") or h.get("node_id") or "")
        body = (h.get("snippet") or h.get("content") or "")[:96]
        key = (did, chunk, body)
        prev = best.get(key)
        if prev is None:
            best[key] = h
            order.append(key)
            continue
        if float(h.get("score") or 0) > float(prev.get("score") or 0):
            best[key] = h
    merged = [best[k] for k in order]
    merged.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return merged[:limit]


def _retrieve_kf_branch(
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    from app.database import SessionLocal
    from app.services.compare_service import validate_document_scope

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return []
        docs = validate_document_scope(
            db,
            user,
            doc_ids,
            min_count=1,
            max_count=20,
            required_level=PermissionLevel.query.value,
            allow_index_only=True,
        )
        from app.services.pageindex_service import partition_documents_by_retrieval_engine

        _pi, kf_docs, _skipped = partition_documents_by_retrieval_engine(db, docs)
        if not kf_docs or not _knowflow_retrieval_available(db, user):
            return []
        kf_ids = [d.id for d in kf_docs]
        return _knowflow_retrieve(db, user, kf_docs, kf_ids, question, limit=limit)
    finally:
        db.close()


def _retrieve_pi_branch(
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    from app.database import SessionLocal
    from app.services.compare_service import validate_document_scope
    from app.services.pageindex_service import (
        partition_documents_by_retrieval_engine,
        retrieve_pageindex_hits_for_qa,
    )

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return []
        docs = validate_document_scope(
            db,
            user,
            doc_ids,
            min_count=1,
            max_count=20,
            required_level=PermissionLevel.query.value,
            allow_index_only=True,
        )
        pi_docs, _kf, _skipped = partition_documents_by_retrieval_engine(db, docs)
        if not pi_docs or limit <= 0:
            return []
        return retrieve_pageindex_hits_for_qa(
            db, user, pi_docs, question, limit=limit
        )
    finally:
        db.close()


def _retrieve_hits_core(
    db: Session,
    user: User,
    docs: list[Document],
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    top_k: int,
    merge_nearby: bool,
) -> tuple[list[dict], str]:
    from app.services.pageindex_service import (
        partition_documents_by_retrieval_engine,
        retrieve_pageindex_hits_for_qa,
    )

    pi_docs, kf_docs, skipped = partition_documents_by_retrieval_engine(db, docs)
    hits: list[dict] = []
    modes: list[str] = []
    kf_available = _knowflow_retrieval_available(db, user)
    total_knowflow_hits = 0

    kf_hits: list[dict] = []
    pi_hits: list[dict] = []
    run_kf = bool(kf_docs and kf_available)
    run_pi = bool(pi_docs and top_k > 0)

    if run_kf and run_pi:
        with ThreadPoolExecutor(
            max_workers=_qa_engine_max_workers(),
            thread_name_prefix="qa-retrieval",
        ) as pool:
            kf_future = pool.submit(
                _retrieve_kf_branch,
                user.id,
                doc_ids,
                question,
                limit=top_k,
            )
            pi_future = pool.submit(
                _retrieve_pi_branch,
                user.id,
                doc_ids,
                question,
                limit=top_k,
            )
            kf_hits = kf_future.result() or []
            pi_hits = pi_future.result() or []
    else:
        if run_kf:
            kf_ids = [d.id for d in kf_docs]
            kf_hits = _knowflow_retrieve(
                db, user, kf_docs, kf_ids, question, limit=top_k
            )
        if run_pi:
            pi_hits = retrieve_pageindex_hits_for_qa(
                db, user, pi_docs, question, limit=top_k
            )

    if kf_hits:
        hits.extend(kf_hits)
        total_knowflow_hits += len(kf_hits)
        modes.append("hybrid")

    remaining = max(0, top_k - len(hits))
    pi_doc_ids_with_hits: set[str] = set()
    if pi_hits and remaining > 0:
        hits.extend(pi_hits[:remaining])
        modes.append("pageindex_tree")
        pi_doc_ids_with_hits = {
            str(h.get("document_id"))
            for h in pi_hits
            if h.get("source") == "pageindex" and h.get("document_id")
        }

    fallback_docs = [
        doc for doc in pi_docs if str(doc.id) not in pi_doc_ids_with_hits
    ]
    remaining = max(0, top_k - len(hits))
    if fallback_docs and remaining > 0 and kf_available:
        fallback_ids = [d.id for d in fallback_docs]
        fb_hits = _knowflow_retrieve(
            db, user, fallback_docs, fallback_ids, question, limit=remaining
        )
        if fb_hits:
            hits.extend(fb_hits)
            total_knowflow_hits += len(fb_hits)
            if "hybrid" not in modes:
                modes.append("hybrid")

    remaining = max(0, top_k - len(hits))
    fallback_all = list(kf_docs) + fallback_docs + skipped
    if fallback_all and remaining > 0 and total_knowflow_hits == 0:
        fallback_ids = [d.id for d in fallback_all]
        local_hits = _local_retrieve(
            db, user, fallback_all, fallback_ids, question, limit=remaining
        )
        if local_hits:
            hits.extend(local_hits)
            modes.append("local")

    if merge_nearby:
        hits = merge_nearby_retrieval_hits(hits)
    hits = hits[:top_k]

    if len(modes) > 1:
        mode = "mixed"
    elif modes:
        mode = modes[0]
    elif hits:
        mode = "local"
    else:
        mode = "none"
    return hits, mode


def _retrieve_hits_worker(
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int | None,
    merge_nearby: bool,
) -> tuple[list[dict], str]:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return [], "none"
        return retrieve_hits_for_qa(
            db,
            user,
            doc_ids,
            question,
            limit=limit,
            merge_nearby=merge_nearby,
        )
    finally:
        db.close()


def retrieve_hits_by_queries(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    questions: list[str],
    *,
    limit_per_query: int | None = None,
    merge_nearby: bool = True,
    max_workers: int | None = None,
) -> dict[str, tuple[list[dict], str]]:
    """并行检索多个 query，返回 query -> (hits, mode) 映射。"""
    unique_queries = list(
        dict.fromkeys(q.strip() for q in questions if (q or "").strip())
    )
    if not unique_queries:
        return {}

    if len(unique_queries) == 1:
        q = unique_queries[0]
        hits, mode = retrieve_hits_for_qa(
            db,
            user,
            doc_ids,
            q,
            limit=limit_per_query,
            merge_nearby=merge_nearby,
        )
        return {q: (hits, mode)}

    workers = _qa_retrieval_max_workers(max_workers)
    workers = min(workers, len(unique_queries))
    out: dict[str, tuple[list[dict], str]] = {}
    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="qa-retrieval-q",
    ) as pool:
        futures = {
            pool.submit(
                _retrieve_hits_worker,
                user.id,
                doc_ids,
                q,
                limit=limit_per_query,
                merge_nearby=merge_nearby,
            ): q
            for q in unique_queries
        }
        for future in as_completed(futures):
            q = futures[future]
            try:
                hits, mode = future.result()
                out[q] = (hits or [], mode or "none")
            except Exception as exc:
                logger.warning("并行检索失败 q=%r: %s", q, exc)
                out[q] = ([], "none")
    return out


def retrieve_merged_hits_for_queries(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    questions: list[str],
    *,
    limit_per_query: int | None = None,
    merge_nearby: bool = False,
    max_total: int | None = None,
    max_workers: int | None = None,
) -> list[dict]:
    """并行执行多路检索 query，合并去重后返回 hit 列表。"""
    unique_queries = list(
        dict.fromkeys(q.strip() for q in questions if (q or "").strip())
    )
    if not unique_queries:
        return []

    cap = max_total if max_total is not None else max(
        20, (limit_per_query or 5) * max(1, len(unique_queries))
    )

    by_query = retrieve_hits_by_queries(
        db,
        user,
        doc_ids,
        unique_queries,
        limit_per_query=limit_per_query,
        merge_nearby=merge_nearby,
        max_workers=max_workers,
    )
    all_hits: list[dict] = []
    for q in unique_queries:
        hits, _mode = by_query.get(q, ([], "none"))
        all_hits.extend(hits)

    if merge_nearby:
        all_hits = merge_nearby_retrieval_hits(all_hits)
    return _merge_hits_by_score(all_hits, limit=cap)


def retrieve_hits_for_qa(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int | None = None,
    merge_nearby: bool = True,
) -> tuple[list[dict], str]:
    settings = get_settings()
    top_k = limit if limit is not None else int(settings.knowledge_retrieval_top_k or 5)
    top_k = max(1, min(top_k, 20))
    from app.services.compare_service import validate_document_scope

    docs = validate_document_scope(
        db,
        user,
        doc_ids,
        min_count=1,
        max_count=20,
        required_level=PermissionLevel.query.value,
        allow_index_only=True,
    )

    return _retrieve_hits_core(
        db,
        user,
        docs,
        doc_ids,
        question,
        top_k=top_k,
        merge_nearby=merge_nearby,
    )


def retrieval_workflow_title(mode: str) -> str:
    return {
        "pageindex_tree": "正在检索相关文档",
        "hybrid": "正在检索相关文档",
        "mixed": "正在检索相关文档",
        "local": "正在检索相关文档",
    }.get(mode, "正在检索相关文档")


def _citation_anchor_key(item: dict) -> tuple:
    anchor = item.get("anchor_json") or {}
    did = str(item.get("document_id") or "")
    page_raw = anchor.get("page")
    try:
        page = int(page_raw) if page_raw is not None else 0
    except (TypeError, ValueError):
        page = 0
    bbox = anchor.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            xs = [float(x) for x in bbox[:4]]
            cx = (xs[0] + xs[2]) / 2
            cy = (xs[1] + xs[3]) / 2
            return (did, page, int(cx // 96), int(cy // 96))
        except (TypeError, ValueError):
            pass
    chunk_id = str(item.get("chunk_id") or "")
    if chunk_id:
        return (did, page, chunk_id)
    return (did, page)


def merge_nearby_retrieval_hits(hits: list[dict]) -> list[dict]:
    """合并同文档同页/邻近位置的检索 hit，减少重复引用编号。"""
    if len(hits) <= 1:
        return hits
    best_by_key: dict[tuple, dict] = {}
    order: list[tuple] = []
    for h in hits:
        key = _citation_anchor_key(h)
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = h
            order.append(key)
            continue
        if float(h.get("score") or 0) > float(prev.get("score") or 0):
            best_by_key[key] = h
    return [best_by_key[k] for k in order]


