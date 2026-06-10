"""文档知识库索引状态：供文档中心列表与详情展示。"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.org import User
from app.models.document import DocumentVersion
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.knowledge_library_service import _enrich_ragflow_doc_meta


def _default_index_meta() -> dict:
    return {
        "knowledge_synced": False,
        "parse_status": "未同步",
        "parse_progress": None,
        "parse_message": None,
        "chunk_count": None,
        "ragflow_document_id": None,
    }


def enrich_document_index_meta(
    db: Session,
    user: User,
    documents: list[Document],
) -> dict[str, dict]:
    """按文档 id 返回索引元数据。"""
    if not documents:
        return {}

    doc_ids = [d.id for d in documents]
    links = list(
        db.scalars(
            select(RagflowDocumentLink).where(
                RagflowDocumentLink.platform_document_id.in_(doc_ids)
            )
        ).all()
    )
    link_by_doc = {str(l.platform_document_id): l for l in links}

    meta_by_doc: dict[str, dict] = {}
    rows_by_dataset: dict[str, list[dict]] = defaultdict(list)

    for doc in documents:
        did = str(doc.id)
        link = link_by_doc.get(did)
        if not link or not link.ragflow_document_id:
            meta_by_doc[did] = _default_index_meta()
            continue
        meta_by_doc[did] = {
            "knowledge_synced": True,
            "parse_status": None,
            "chunk_count": None,
            "ragflow_document_id": link.ragflow_document_id,
        }
        rows_by_dataset[link.dataset_id].append(
            {
                "document_id": did,
                "ragflow_document_id": link.ragflow_document_id,
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
            ps = row.get("parse_status")
            meta_by_doc[did]["parse_status"] = ps or "已索引"
            meta_by_doc[did]["chunk_count"] = row.get("chunk_count")
            meta_by_doc[did]["parse_progress"] = row.get("parse_progress")
            meta_by_doc[did]["parse_message"] = row.get("parse_message")

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
            ps = row.get("parse_status")
            meta_by_ver[vid]["parse_status"] = ps or "已索引"
            meta_by_ver[vid]["chunk_count"] = row.get("chunk_count")
            meta_by_ver[vid]["parse_progress"] = row.get("parse_progress")
            meta_by_ver[vid]["parse_message"] = row.get("parse_message")

    return meta_by_ver


def apply_index_meta_to_item(item, meta: dict | None):
    """将索引字段写入 DocumentListItem / DocumentDetail。"""
    m = meta or _default_index_meta()
    return item.model_copy(
        update={
            "knowledge_synced": bool(m.get("knowledge_synced")),
            "parse_status": m.get("parse_status"),
            "parse_progress": m.get("parse_progress"),
            "parse_message": m.get("parse_message"),
            "chunk_count": m.get("chunk_count"),
            "ragflow_document_id": m.get("ragflow_document_id"),
        }
    )
