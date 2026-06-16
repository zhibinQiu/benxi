"""平台运行大屏统计。"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.features.registry import all_plugins, ensure_plugins_loaded
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.org import User, UserStatus
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.online_presence_service import ONLINE_WINDOW_MINUTES, count_users_online

logger = logging.getLogger(__name__)

# RAGFlow run=3 表示解析/索引已完成
RAGFLOW_RUN_COMPLETED = "3"


def _active_document_filters():
    has_uploaded_version = exists(
        select(1).where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.file_size > 0,
        )
    )
    return (
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        has_uploaded_version,
    )


def _ragflow_doc_id(item: dict) -> str:
    return str(item.get("id") or item.get("doc_id") or "")


def _fetch_run_status_map(
    rag: RagflowClient,
    dataset_id: str,
    needed_ids: set[str],
) -> dict[str, str]:
    """按 dataset 拉取 RAGFlow 文档 run 状态，仅保留 needed_ids。"""
    if not needed_ids:
        return {}
    run_by_id: dict[str, str] = {}
    page = 1
    page_size = max(len(needed_ids), 30)
    total = 0
    while True:
        try:
            docs, total = rag.list_dataset_documents(
                dataset_id, page=page, page_size=page_size
            )
        except RagflowError as exc:
            logger.warning("拉取索引状态失败 dataset=%s: %s", dataset_id, exc)
            break
        except Exception as exc:
            logger.warning("拉取索引状态异常 dataset=%s: %s", dataset_id, exc)
            break
        for item in docs:
            rid = _ragflow_doc_id(item)
            if rid and rid in needed_ids:
                run_by_id[rid] = str(item.get("run", ""))
        if len(run_by_id) >= len(needed_ids):
            break
        if not docs:
            break
        if total and page * page_size >= total:
            break
        page += 1
    return run_by_id


def _indexed_doc_ids_from_version_links(db: Session) -> set[uuid.UUID]:
    """与文档中心一致：版本映射上已写入 index_completed_at 的活跃文档。"""
    active_doc_filters = _active_document_filters()
    rows = db.execute(
        select(RagflowDocumentVersionLink.platform_document_id)
        .join(
            Document,
            RagflowDocumentVersionLink.platform_document_id == Document.id,
        )
        .where(
            *active_doc_filters,
            RagflowDocumentVersionLink.index_completed_at.is_not(None),
            RagflowDocumentVersionLink.ragflow_document_id.is_not(None),
            RagflowDocumentVersionLink.ragflow_document_id != "",
        )
        .distinct()
    ).all()
    return {row[0] for row in rows}


def _collect_ragflow_link_candidates(
    db: Session,
) -> list[tuple[uuid.UUID, str, str]]:
    """活跃文档上所有 RAGFlow 映射（版本级 + canonical），供在线校验 run 状态。"""
    active_doc_filters = _active_document_filters()
    seen: set[tuple[uuid.UUID, str]] = set()
    candidates: list[tuple[uuid.UUID, str, str]] = []

    def _add(doc_id: uuid.UUID, rag_id: str | None, dataset_id: str | None) -> None:
        rid = str(rag_id or "").strip()
        ds = str(dataset_id or "").strip()
        if not rid or not ds:
            return
        key = (doc_id, rid)
        if key in seen:
            return
        seen.add(key)
        candidates.append((doc_id, rid, ds))

    version_rows = db.execute(
        select(
            RagflowDocumentVersionLink.platform_document_id,
            RagflowDocumentVersionLink.ragflow_document_id,
            RagflowDocumentVersionLink.dataset_id,
        )
        .join(
            Document,
            RagflowDocumentVersionLink.platform_document_id == Document.id,
        )
        .where(
            *active_doc_filters,
            RagflowDocumentVersionLink.ragflow_document_id.is_not(None),
            RagflowDocumentVersionLink.ragflow_document_id != "",
        )
    ).all()
    for doc_id, rag_id, dataset_id in version_rows:
        _add(doc_id, rag_id, dataset_id)

    canonical_rows = db.execute(
        select(
            RagflowDocumentLink.platform_document_id,
            RagflowDocumentLink.ragflow_document_id,
            RagflowDocumentLink.dataset_id,
        )
        .join(Document, RagflowDocumentLink.platform_document_id == Document.id)
        .where(
            *active_doc_filters,
            RagflowDocumentLink.ragflow_document_id.is_not(None),
            RagflowDocumentLink.ragflow_document_id != "",
        )
    ).all()
    for doc_id, rag_id, dataset_id in canonical_rows:
        _add(doc_id, rag_id, dataset_id)

    return candidates


def _indexed_doc_ids_from_ragflow(
    db: Session,
    candidates: list[tuple[uuid.UUID, str, str]],
) -> set[uuid.UUID]:
    """KnowFlow 可达时，按 RAGFlow run=3 补充尚未写入 index_completed_at 的文档。"""
    if not candidates:
        return set()

    from app.domains.knowledge import knowledge
    from app.services.ragflow_scope_service import _privileged_rag_client

    if not knowledge.stack_reachable():
        return set()

    rag = _privileged_rag_client(db)
    if not rag or not rag.health_ok():
        return set()

    by_dataset: dict[str, set[str]] = defaultdict(set)
    doc_id_by_rag: dict[str, uuid.UUID] = {}
    for doc_id, rag_id, dataset_id in candidates:
        by_dataset[dataset_id].add(rag_id)
        doc_id_by_rag[rag_id] = doc_id

    indexed_doc_ids: set[uuid.UUID] = set()
    for dataset_id, rag_ids in by_dataset.items():
        run_by_rag = _fetch_run_status_map(rag, dataset_id, rag_ids)
        for rid in rag_ids:
            if run_by_rag.get(rid) == RAGFLOW_RUN_COMPLETED:
                indexed_doc_ids.add(doc_id_by_rag[rid])
    return indexed_doc_ids


def _count_documents_indexed(db: Session) -> int:
    """已索引文档数：与文档中心一致，优先 DB 完成标记，KnowFlow 可达时再按 run=3 补充。"""
    indexed_doc_ids = _indexed_doc_ids_from_version_links(db)
    candidates = _collect_ragflow_link_candidates(db)
    indexed_doc_ids |= _indexed_doc_ids_from_ragflow(db, candidates)
    return len(indexed_doc_ids)


def collect_platform_dashboard_stats(db: Session) -> dict:
    """汇总平台级运行指标（文档按实体计数，不重复统计版本）。"""
    active_doc_filters = _active_document_filters()

    documents_total = int(
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(*active_doc_filters)
        )
        or 0
    )

    documents_indexed = _count_documents_indexed(db)

    ensure_plugins_loaded()
    catalog_plugins = [p for p in all_plugins() if getattr(p, "show_in_catalog", True)]
    features_total = len(catalog_plugins)
    features_pending = sum(1 for p in catalog_plugins if not p.enabled)

    users_registered = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.status == UserStatus.active.value)
        )
        or 0
    )

    online_since = datetime.now(timezone.utc) - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    users_online = count_users_online()
    if users_online is None:
        users_online = int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.status == UserStatus.active.value,
                    User.last_seen_at.is_not(None),
                    User.last_seen_at >= online_since,
                )
            )
            or 0
        )

    return {
        "documents_total": documents_total,
        "documents_indexed": documents_indexed,
        "features_total": features_total,
        "features_pending": features_pending,
        "users_registered": users_registered,
        "users_online": users_online,
        "collected_at": time.time(),
    }
