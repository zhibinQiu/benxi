"""文档版本级 RAGFlow 索引映射与检索。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.document_service import resolve_current_version


def get_version_link_by_version_id(
    db: Session, version_id: uuid.UUID
) -> RagflowDocumentVersionLink | None:
    return db.scalar(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.platform_version_id == version_id
        )
    )


def get_version_link_by_ragflow_id(
    db: Session, ragflow_document_id: str
) -> RagflowDocumentVersionLink | None:
    rid = (ragflow_document_id or "").strip()
    if not rid:
        return None
    return db.scalar(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.ragflow_document_id == rid
        )
    )


def list_version_links_for_document(
    db: Session, document_id: uuid.UUID
) -> list[RagflowDocumentVersionLink]:
    return list(
        db.scalars(
            select(RagflowDocumentVersionLink)
            .where(RagflowDocumentVersionLink.platform_document_id == document_id)
            .order_by(RagflowDocumentVersionLink.version_no.desc())
        ).all()
    )


def resolve_index_link(
    db: Session,
    document: Document,
    *,
    version_id: uuid.UUID | None = None,
) -> tuple[RagflowDocumentVersionLink | None, DocumentVersion | None]:
    """解析用于读切片/检索的版本索引；默认当前版本。"""
    version: DocumentVersion | None = None
    if version_id:
        version = db.get(DocumentVersion, version_id)
        if not version or version.document_id != document.id:
            return None, None
    else:
        version = resolve_current_version(db, document)
    if not version:
        return None, None
    vl = get_version_link_by_version_id(db, version.id)
    return vl, version


def upsert_version_link(
    db: Session,
    *,
    document: Document,
    version: DocumentVersion,
    ragflow_document_id: str,
    dataset_id: str,
    file_name: str,
    platform_user_id: uuid.UUID,
    parser_id: str | None = None,
) -> RagflowDocumentVersionLink:
    vl = get_version_link_by_version_id(db, version.id)
    if vl:
        vl.ragflow_document_id = ragflow_document_id
        vl.dataset_id = dataset_id
        vl.file_name = file_name
        vl.platform_user_id = platform_user_id
        vl.version_no = version.version_no
        if parser_id:
            vl.parser_id = parser_id
    else:
        vl = RagflowDocumentVersionLink(
            platform_document_id=document.id,
            platform_version_id=version.id,
            version_no=version.version_no,
            platform_user_id=platform_user_id,
            ragflow_document_id=ragflow_document_id,
            dataset_id=dataset_id,
            file_name=file_name,
            parser_id=parser_id,
        )
        db.add(vl)
    db.flush()
    return vl


def upsert_canonical_link(
    db: Session,
    *,
    document: Document,
    ragflow_document_id: str,
    dataset_id: str,
    file_name: str,
    platform_user_id: uuid.UUID,
) -> RagflowDocumentLink:
    existing = db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document.id
        )
    )
    if existing:
        existing.ragflow_document_id = ragflow_document_id
        existing.dataset_id = dataset_id
        existing.platform_user_id = platform_user_id
        existing.file_name = file_name
        return existing
    row = RagflowDocumentLink(
        platform_document_id=document.id,
        platform_user_id=platform_user_id,
        ragflow_document_id=ragflow_document_id,
        dataset_id=dataset_id,
        file_name=file_name,
    )
    db.add(row)
    db.flush()
    return row


def ragflow_to_platform_version_map(
    db: Session, ragflow_doc_ids: list[str]
) -> dict[str, dict]:
    """ragflow_document_id → {platform_document_id, document_version_id, version_no}。"""
    ids = [x for x in ragflow_doc_ids if x]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    for row in db.scalars(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.ragflow_document_id.in_(ids)
        )
    ).all():
        out[row.ragflow_document_id] = {
            "platform_document_id": str(row.platform_document_id),
            "document_version_id": str(row.platform_version_id)
            if row.platform_version_id
            else None,
            "version_no": row.version_no,
        }
    missing = [rid for rid in ids if rid not in out]
    if missing:
        for row in db.scalars(
            select(RagflowDocumentLink).where(
                RagflowDocumentLink.ragflow_document_id.in_(missing)
            )
        ).all():
            out[row.ragflow_document_id] = {
                "platform_document_id": str(row.platform_document_id),
                "document_version_id": None,
                "version_no": None,
            }
    return out


def backfill_version_links_from_canonical(db: Session) -> int:
    """将既有 canonical 映射回填为当前版本的 version link。"""
    created = 0
    for link in db.scalars(select(RagflowDocumentLink)).all():
        doc = db.get(Document, link.platform_document_id)
        if not doc or doc.deleted_at:
            continue
        version = resolve_current_version(db, doc)
        if not version:
            continue
        if get_version_link_by_version_id(db, version.id):
            continue
        upsert_version_link(
            db,
            document=doc,
            version=version,
            ragflow_document_id=link.ragflow_document_id,
            dataset_id=link.dataset_id,
            file_name=link.file_name,
            platform_user_id=link.platform_user_id,
        )
        created += 1
    return created
