"""文档知识库索引状态：供文档中心列表与详情展示。"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.knowledge_library_service import _enrich_ragflow_doc_meta

_INDEX_DONE_LABELS = frozenset({"已完成", "已索引"})
INDEX_READY_STATUSES = _INDEX_DONE_LABELS


def is_index_ready_meta(meta: dict | None) -> bool:
    """文档是否已成功索引、可用于知识检索（全平台统一判据）。"""
    if not meta or not meta.get("knowledge_synced"):
        return False
    return (meta.get("parse_status") or "") in INDEX_READY_STATUSES


def _apply_db_ready_override(
    meta_by_doc: dict[str, dict],
    db_only_meta: dict[str, dict],
) -> None:
    """库内 index_completed_at 已就绪时，覆盖 KnowFlow 元数据缓存的滞后状态。"""
    for did, db_meta in db_only_meta.items():
        if not is_index_ready_meta(db_meta):
            continue
        live = meta_by_doc.get(did)
        if live is None:
            meta_by_doc[did] = dict(db_meta)
            continue
        live["parse_status"] = db_meta.get("parse_status")
        live["knowledge_synced"] = True
        for key in (
            "indexed_version_id",
            "indexed_version_no",
            "ragflow_document_id",
            "parse_progress",
            "chunk_count",
        ):
            if db_meta.get(key) is not None:
                live[key] = db_meta[key]


def _default_index_meta() -> dict:
    return {
        "knowledge_synced": False,
        "parse_status": "未同步",
        "parse_progress": None,
        "parse_message": None,
        "chunk_count": None,
        "ragflow_document_id": None,
        "indexed_version_id": None,
        "indexed_version_no": None,
    }


def _merge_enriched_row(meta: dict, row: dict) -> None:
    fetch_ok = row.get("_meta_fetch_ok")
    ps = row.get("parse_status")
    if ps is not None:
        meta["parse_status"] = ps
    elif fetch_ok and meta.get("knowledge_synced"):
        meta["parse_status"] = "索引失效"
    elif fetch_ok:
        meta["parse_status"] = "索引失效"
    # fetch 失败时不默认「解析中」，避免 list API 异常时误导用户
    meta["chunk_count"] = row.get("chunk_count")
    meta["parse_progress"] = row.get("parse_progress")
    meta["parse_message"] = row.get("parse_message")


def _maybe_mark_version_index_completed(
    db: Session, link: RagflowDocumentVersionLink | None, parse_status: str | None
) -> None:
    if not link or not parse_status or parse_status not in _INDEX_DONE_LABELS:
        return
    if link.index_completed_at is None:
        link.index_completed_at = datetime.now(timezone.utc)
        db.flush()


def _resolve_document_rag_link(
    db: Session,
    doc: Document,
    canonical_by_doc: dict[str, RagflowDocumentLink],
) -> tuple[str | None, str | None, uuid.UUID | None]:
    """文档级展示：优先最后索引成功版本；无成功版本时用当前版本跟踪进行中任务。"""
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import (
        get_version_link_by_version_id,
        resolve_latest_indexed_version,
    )

    indexed_ver = resolve_latest_indexed_version(db, doc)
    if indexed_ver:
        vl = get_version_link_by_version_id(db, indexed_ver.id)
        if vl and vl.ragflow_document_id:
            return vl.dataset_id, vl.ragflow_document_id, indexed_ver.id

    current = resolve_current_version(db, doc)
    if current:
        vl = get_version_link_by_version_id(db, current.id)
        if vl and vl.ragflow_document_id:
            return vl.dataset_id, vl.ragflow_document_id, current.id

    link = canonical_by_doc.get(str(doc.id))
    if link and link.ragflow_document_id:
        return link.dataset_id, link.ragflow_document_id, None
    return None, None, None


def _meta_from_version_link(link: RagflowDocumentVersionLink | None) -> dict:
    if not link or not link.ragflow_document_id:
        return _default_index_meta()
    version_id = str(link.platform_version_id) if link.platform_version_id else None
    if link.index_completed_at:
        return {
            "knowledge_synced": True,
            "parse_status": "已索引",
            "parse_progress": 100,
            "parse_message": None,
            "chunk_count": None,
            "ragflow_document_id": link.ragflow_document_id,
            "indexed_version_id": version_id,
            "indexed_version_no": link.version_no,
        }
    return {
        "knowledge_synced": True,
        "parse_status": "未解析",
        "parse_progress": None,
        "parse_message": None,
        "chunk_count": None,
        "ragflow_document_id": link.ragflow_document_id,
        "indexed_version_id": version_id,
        "indexed_version_no": link.version_no,
    }


def _batch_version_links_by_document(
    db: Session, doc_ids: list[uuid.UUID]
) -> dict[str, list[RagflowDocumentVersionLink]]:
    if not doc_ids:
        return {}
    rows = list(
        db.scalars(
            select(RagflowDocumentVersionLink).where(
                RagflowDocumentVersionLink.platform_document_id.in_(doc_ids)
            )
        ).all()
    )
    grouped: dict[str, list[RagflowDocumentVersionLink]] = defaultdict(list)
    for link in rows:
        grouped[str(link.platform_document_id)].append(link)
    return grouped


def _pick_document_version_link(
    doc: Document,
    *,
    canonical: RagflowDocumentLink | None,
    version_links: list[RagflowDocumentVersionLink],
) -> RagflowDocumentVersionLink | None:
    indexed = [l for l in version_links if l.index_completed_at]
    if indexed:
        return max(indexed, key=lambda item: (item.version_no or 0, item.updated_at or item.created_at))
    if doc.current_version_id:
        for link in version_links:
            if link.platform_version_id == doc.current_version_id and link.ragflow_document_id:
                return link
    if canonical and canonical.ragflow_document_id:
        for link in version_links:
            if link.ragflow_document_id == canonical.ragflow_document_id:
                return link
    for link in version_links:
        if link.ragflow_document_id:
            return link
    return None


def _enrich_document_index_meta_db_only(
    db: Session,
    documents: list[Document],
    *,
    link_by_doc: dict[str, RagflowDocumentLink],
    version_links_by_doc: dict[str, list[RagflowDocumentVersionLink]],
) -> dict[str, dict]:
    meta_by_doc: dict[str, dict] = {}
    for doc in documents:
        did = str(doc.id)
        canonical = link_by_doc.get(did)
        version_links = version_links_by_doc.get(did, [])
        picked = _pick_document_version_link(
            doc, canonical=canonical, version_links=version_links
        )
        if picked:
            meta_by_doc[did] = _meta_from_version_link(picked)
        elif canonical and canonical.ragflow_document_id:
            meta_by_doc[did] = {
                "knowledge_synced": True,
                "parse_status": "未解析",
                "parse_progress": None,
                "parse_message": None,
                "chunk_count": None,
                "ragflow_document_id": canonical.ragflow_document_id,
                "indexed_version_id": None,
                "indexed_version_no": None,
            }
        else:
            meta_by_doc[did] = _default_index_meta()
    return meta_by_doc


def enrich_document_index_meta(
    db: Session,
    user: User,
    documents: list[Document],
    *,
    live_ragflow: bool | None = None,
) -> dict[str, dict]:
    """按文档 id 返回索引元数据（绑定最后索引成功版本）。"""
    if not documents:
        return {}

    from app.config import get_settings

    if live_ragflow is None:
        live_ragflow = get_settings().knowledge_list_live_index_meta

    doc_ids = [d.id for d in documents]
    links = list(
        db.scalars(
            select(RagflowDocumentLink).where(
                RagflowDocumentLink.platform_document_id.in_(doc_ids)
            )
        ).all()
    )
    link_by_doc = {str(l.platform_document_id): l for l in links}
    version_links_by_doc = _batch_version_links_by_document(db, doc_ids)

    if not live_ragflow:
        return _enrich_document_index_meta_db_only(
            db,
            documents,
            link_by_doc=link_by_doc,
            version_links_by_doc=version_links_by_doc,
        )

    meta_by_doc: dict[str, dict] = {}
    rows_by_dataset: dict[str, list[dict]] = defaultdict(list)
    version_link_by_doc: dict[str, RagflowDocumentVersionLink | None] = {}

    for doc in documents:
        did = str(doc.id)
        dataset_id, ragflow_id, version_id = _resolve_document_rag_link(
            db, doc, link_by_doc
        )
        if not ragflow_id or not dataset_id:
            meta_by_doc[did] = _default_index_meta()
            continue
        vl = None
        if version_id:
            for link in version_links_by_doc.get(did, []):
                if link.platform_version_id == version_id:
                    vl = link
                    break
        version_link_by_doc[did] = vl
        meta_by_doc[did] = {
            "knowledge_synced": True,
            "parse_status": None,
            "parse_progress": None,
            "parse_message": None,
            "chunk_count": None,
            "ragflow_document_id": ragflow_id,
            "indexed_version_id": str(version_id) if version_id else None,
            "indexed_version_no": vl.version_no if vl else None,
        }
        rows_by_dataset[dataset_id].append(
            {
                "document_id": did,
                "ragflow_document_id": ragflow_id,
                "parse_status": None,
                "chunk_count": None,
            }
        )

    for dataset_id, rows in rows_by_dataset.items():
        _enrich_ragflow_doc_meta(db, user, dataset_id, rows)
        for row in rows:
            did = str(row["document_id"])
            if did not in meta_by_doc:
                continue
            _merge_enriched_row(meta_by_doc[did], row)
            _maybe_mark_version_index_completed(
                db, version_link_by_doc.get(did), meta_by_doc[did].get("parse_status")
            )

    db_only = _enrich_document_index_meta_db_only(
        db,
        documents,
        link_by_doc=link_by_doc,
        version_links_by_doc=version_links_by_doc,
    )
    _apply_db_ready_override(meta_by_doc, db_only)
    return meta_by_doc


def enrich_version_index_meta(
    db: Session,
    user: User,
    versions: list[DocumentVersion],
) -> dict[str, dict]:
    """按版本 id 返回索引元数据（历史版本切片独立保留）。"""
    if not versions:
        return {}
    version_ids = [v.id for v in versions]
    links = list(
        db.scalars(
            select(RagflowDocumentVersionLink).where(
                RagflowDocumentVersionLink.platform_version_id.in_(version_ids)
            )
        ).all()
    )
    link_by_ver = {str(l.platform_version_id): l for l in links if l.platform_version_id}

    meta_by_ver: dict[str, dict] = {}
    rows_by_dataset: dict[str, list[dict]] = defaultdict(list)

    for ver in versions:
        vid = str(ver.id)
        link = link_by_ver.get(vid)
        if not link or not link.ragflow_document_id:
            meta_by_ver[vid] = _default_index_meta()
            continue
        meta_by_ver[vid] = {
            "knowledge_synced": True,
            "parse_status": None,
            "chunk_count": None,
            "ragflow_document_id": link.ragflow_document_id,
            "version_no": link.version_no,
        }
        rows_by_dataset[link.dataset_id].append(
            {
                "document_id": vid,
                "ragflow_document_id": link.ragflow_document_id,
                "parse_status": None,
                "chunk_count": None,
            }
        )

    for dataset_id, rows in rows_by_dataset.items():
        _enrich_ragflow_doc_meta(db, user, dataset_id, rows)
        for row in rows:
            vid = str(row["document_id"])
            if vid not in meta_by_ver:
                continue
            _merge_enriched_row(meta_by_ver[vid], row)
            _maybe_mark_version_index_completed(
                db, link_by_ver.get(vid), meta_by_ver[vid].get("parse_status")
            )
            link = link_by_ver.get(vid)
            if link and link.index_completed_at:
                meta_by_ver[vid]["parse_status"] = "已索引"
                meta_by_ver[vid]["knowledge_synced"] = True

    return meta_by_ver


def apply_index_meta_to_knowledge_row(row: dict, meta: dict | None) -> None:
    """将统一索引元数据写入知识检索树 / 库列表行（就地更新）。"""
    m = meta or _default_index_meta()
    row["knowledge_synced"] = bool(m.get("knowledge_synced"))
    row["parse_status"] = m.get("parse_status")
    row["index_ready"] = is_index_ready_meta(m)
    if m.get("ragflow_document_id") and not row.get("ragflow_document_id"):
        row["ragflow_document_id"] = m.get("ragflow_document_id")


def enrich_knowledge_document_rows(
    db: Session,
    user: User,
    rows: list[dict],
    documents: list[Document],
) -> None:
    """知识检索相关 UI 的唯一索引状态读取入口。"""
    if not rows or not documents:
        return
    meta_by_doc = enrich_document_index_meta(db, user, list(documents), live_ragflow=True)
    for row in rows:
        did = str(row.get("document_id") or "")
        apply_index_meta_to_knowledge_row(row, meta_by_doc.get(did))


def apply_index_meta_to_item(item, meta: dict | None):
    """将索引字段写入 DocumentListItem / DocumentDetail。"""
    m = meta or _default_index_meta()
    update = {
        "knowledge_synced": bool(m.get("knowledge_synced")),
        "parse_status": m.get("parse_status"),
        "parse_progress": m.get("parse_progress"),
        "parse_message": m.get("parse_message"),
        "chunk_count": m.get("chunk_count"),
        "ragflow_document_id": m.get("ragflow_document_id"),
    }
    indexed_vid = m.get("indexed_version_id")
    if indexed_vid:
        try:
            update["indexed_version_id"] = uuid.UUID(str(indexed_vid))
        except ValueError:
            update["indexed_version_id"] = None
    else:
        update["indexed_version_id"] = None
    update["indexed_version_no"] = m.get("indexed_version_no")
    return item.model_copy(update=update)
