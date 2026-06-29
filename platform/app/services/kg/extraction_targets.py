"""批量抽离目标收集 — 按 scope 与文档权限筛选。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.models.org import User

SCOPE_KNOWLEDGE = "knowledge"
SCOPE_PLATFORM = "platform"

_SCOPE_LABELS = {
    SCOPE_KNOWLEDGE: "知识库",
    SCOPE_PLATFORM: "平台库",
}


@dataclass(frozen=True)
class ExtractionTargetPlan:
    pending: list[tuple[uuid.UUID, uuid.UUID]]
    already_extracted_count: int
    total_candidates: int


def _resolve_version(
    db: Session,
    doc: Document,
    version_id: uuid.UUID | None,
) -> DocumentVersion | None:
    from app.services.kg_extraction_service import _resolve_version as resolve_version

    return resolve_version(db, doc, version_id)


def _already_extracted_for_version(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> bool:
    from app.services.kg_extraction_service import _already_extracted_for_version as check

    return check(db, user, document_id, version_id)


def collect_extraction_targets(
    db: Session,
    user: User,
    *,
    scope: str,
    force: bool = False,
) -> ExtractionTargetPlan:
    """收集批量抽离目标。

    knowledge：仅当前用户拥有完全权限（可修改）且已完成索引的文档。
    platform：当前用户可查询的平台文档库。
    """
    from app.core.document_scope import can_modify_document, can_query_document
    from app.services.document_service import get_document

    pending: list[tuple[uuid.UUID, uuid.UUID]] = []
    already_extracted_count = 0
    seen: set[str] = set()

    def _consider(doc: Document, version: DocumentVersion) -> None:
        nonlocal already_extracted_count
        key = str(doc.id)
        if key in seen:
            return
        seen.add(key)
        if not force and _already_extracted_for_version(db, user, doc.id, version.id):
            already_extracted_count += 1
            return
        pending.append((doc.id, version.id))

    if scope == SCOPE_KNOWLEDGE:
        from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
        from app.services.ragflow_version_link_service import resolve_latest_indexed_version

        doc_ids = db.scalars(
            select(RagflowDocumentVersionLink.platform_document_id)
            .where(RagflowDocumentVersionLink.index_completed_at.is_not(None))
            .distinct()
        ).all()
        for doc_id in doc_ids:
            doc = get_document(db, doc_id)
            if not doc or doc.deleted_at:
                continue
            if not can_modify_document(db, user, doc):
                continue
            ver = resolve_latest_indexed_version(db, doc)
            if not ver:
                continue
            _consider(doc, ver)
        return ExtractionTargetPlan(
            pending=pending,
            already_extracted_count=already_extracted_count,
            total_candidates=len(seen),
        )

    if scope == SCOPE_PLATFORM:
        from app.services.documents.listing import list_queryable_documents

        page = 1
        page_size = 200
        while True:
            docs, total = list_queryable_documents(
                db, user, page=page, page_size=page_size
            )
            if not docs:
                break
            for doc in docs:
                if not can_query_document(db, user, doc):
                    continue
                ver = _resolve_version(db, doc, None)
                if not ver:
                    continue
                _consider(doc, ver)
            if page * page_size >= total:
                break
            page += 1
        return ExtractionTargetPlan(
            pending=pending,
            already_extracted_count=already_extracted_count,
            total_candidates=len(seen),
        )

    raise ValueError(f"invalid scope: {scope}")
