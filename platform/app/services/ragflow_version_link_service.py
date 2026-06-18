"""文档版本级 RAGFlow 索引映射与检索。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    SCOPE_TEAM,
)
from app.models.document import Document, DocumentVersion
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
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


def find_existing_knowflow_version_link_by_content(
    db: Session,
    *,
    dataset_id: str,
    checksum: str,
    file_size: int | None = None,
    exclude_version_id: uuid.UUID | None = None,
    require_indexed: bool = False,
) -> RagflowDocumentVersionLink | None:
    """同知识库内按 MD5（及 file_size）查找已有 RAGFlow 映射；可含解析中的副本。"""
    ds_id = (dataset_id or "").strip()
    digest = (checksum or "").strip().lower()
    if not ds_id or len(digest) != 32:
        return None

    stmt = (
        select(RagflowDocumentVersionLink)
        .join(
            DocumentVersion,
            DocumentVersion.id == RagflowDocumentVersionLink.platform_version_id,
        )
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            RagflowDocumentVersionLink.dataset_id == ds_id,
            DocumentVersion.checksum == digest,
            RagflowDocumentVersionLink.ragflow_document_id.is_not(None),
            RagflowDocumentVersionLink.ragflow_document_id != "",
            Document.deleted_at.is_(None),
        )
    )
    if require_indexed:
        stmt = stmt.where(RagflowDocumentVersionLink.index_completed_at.is_not(None))
    if file_size is not None and int(file_size) > 0:
        stmt = stmt.where(DocumentVersion.file_size == int(file_size))
    if exclude_version_id is not None:
        stmt = stmt.where(DocumentVersion.id != exclude_version_id)

    if require_indexed:
        stmt = stmt.order_by(RagflowDocumentVersionLink.index_completed_at.desc())
    else:
        stmt = stmt.order_by(
            RagflowDocumentVersionLink.index_completed_at.desc().nullslast(),
            RagflowDocumentVersionLink.updated_at.desc(),
        )
    return db.scalar(stmt.limit(1))


def _content_reuse_scope_filter(document: Document):
    """企业级内容复用：同 MD5 可跨文件名/跨文档赋权共享，个人库不跨用户复用他人个人索引。"""
    scope = (document.scope or SCOPE_PERSONAL).strip()
    if scope == SCOPE_COMPANY:
        return Document.scope == SCOPE_COMPANY
    if scope in (SCOPE_DEPARTMENT, SCOPE_TEAM):
        if document.dept_id:
            return or_(
                Document.scope == SCOPE_COMPANY,
                Document.dept_id == document.dept_id,
            )
        return Document.scope.in_((SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_TEAM))
    # 个人库：跨库仅复用组织级已索引副本，不复用他人个人库
    from app.config import get_settings

    if not get_settings().knowflow_content_reuse_allow_personal_from_org:
        return Document.scope == SCOPE_PERSONAL
    return Document.scope.in_((SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_TEAM))


def find_reusable_knowflow_version_link_for_document(
    db: Session,
    *,
    document: Document,
    target_dataset_id: str,
    checksum: str,
    file_size: int | None = None,
    exclude_version_id: uuid.UUID | None = None,
    require_indexed: bool = True,
) -> RagflowDocumentVersionLink | None:
    """按内容 MD5 查找可复用索引：先同库，再按分级策略跨库（文件名可不同）。"""
    target_ds = (target_dataset_id or "").strip()
    digest = (checksum or "").strip().lower()
    if len(digest) != 32:
        return None

    same_ds = find_existing_knowflow_version_link_by_content(
        db,
        dataset_id=target_ds,
        checksum=digest,
        file_size=file_size,
        exclude_version_id=exclude_version_id,
        require_indexed=require_indexed,
    )
    if same_ds:
        return same_ds

    stmt = (
        select(RagflowDocumentVersionLink)
        .join(
            DocumentVersion,
            DocumentVersion.id == RagflowDocumentVersionLink.platform_version_id,
        )
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            DocumentVersion.checksum == digest,
            RagflowDocumentVersionLink.ragflow_document_id.is_not(None),
            RagflowDocumentVersionLink.ragflow_document_id != "",
            Document.deleted_at.is_(None),
            _content_reuse_scope_filter(document),
        )
    )
    if target_ds:
        stmt = stmt.where(RagflowDocumentVersionLink.dataset_id != target_ds)
    if require_indexed:
        stmt = stmt.where(RagflowDocumentVersionLink.index_completed_at.is_not(None))
    if file_size is not None and int(file_size) > 0:
        stmt = stmt.where(DocumentVersion.file_size == int(file_size))
    if exclude_version_id is not None:
        stmt = stmt.where(DocumentVersion.id != exclude_version_id)

    scope_rank = {
        SCOPE_COMPANY: 0,
        SCOPE_DEPARTMENT: 1,
        SCOPE_TEAM: 2,
        SCOPE_PERSONAL: 3,
    }
    if require_indexed:
        stmt = stmt.order_by(
            RagflowDocumentVersionLink.index_completed_at.desc(),
        )
    else:
        stmt = stmt.order_by(
            RagflowDocumentVersionLink.index_completed_at.desc().nullslast(),
            RagflowDocumentVersionLink.updated_at.desc(),
        )
    candidates = list(db.scalars(stmt.limit(20)).all())
    if not candidates:
        return None
    candidates.sort(
        key=lambda link: (
            0 if (link.index_completed_at is not None) else 1,
            scope_rank.get(
                (
                    db.get(Document, link.platform_document_id).scope
                    if db.get(Document, link.platform_document_id)
                    else SCOPE_PERSONAL
                ),
                9,
            ),
        )
    )
    return candidates[0]


def find_reusable_knowflow_version_link(
    db: Session,
    *,
    dataset_id: str,
    checksum: str,
    file_name: str = "",
    file_size: int | None = None,
    exclude_version_id: uuid.UUID | None = None,
) -> RagflowDocumentVersionLink | None:
    """同知识库内按内容 MD5 查找已成功索引的版本，用于复用 RAGFlow 文档（文件名可不同）。"""
    _ = file_name
    return find_existing_knowflow_version_link_by_content(
        db,
        dataset_id=dataset_id,
        checksum=checksum,
        file_size=file_size,
        exclude_version_id=exclude_version_id,
        require_indexed=True,
    )


def count_ragflow_document_references(
    db: Session,
    ragflow_document_id: str,
    *,
    exclude_document_id: uuid.UUID | None = None,
) -> int:
    """统计仍引用该 RAGFlow 文档的平台映射数（用于安全删除共享索引）。"""
    rid = (ragflow_document_id or "").strip()
    if not rid:
        return 0
    n = 0
    for model in (
        RagflowDocumentVersionLink,
        RagflowDocumentMirrorLink,
        RagflowDocumentLink,
    ):
        col = model.ragflow_document_id
        stmt = select(func.count()).where(col == rid)
        if exclude_document_id is not None and hasattr(model, "platform_document_id"):
            stmt = stmt.where(model.platform_document_id != exclude_document_id)
        n += int(db.scalar(stmt) or 0)
    return n


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


def resolve_latest_indexed_version(
    db: Session, document: Document
) -> DocumentVersion | None:
    """问答/检索与文档展示：已索引成功的最高版本号。"""
    from app.services.documents.crud import is_version_uploaded

    for link in list_version_links_for_document(db, document.id):
        if not (link.ragflow_document_id or "").strip():
            continue
        if link.index_completed_at is None:
            continue
        ver = db.get(DocumentVersion, link.platform_version_id)
        if ver and is_version_uploaded(ver):
            return ver
    return None


def mark_version_index_completed(
    db: Session, version_id: uuid.UUID
) -> RagflowDocumentVersionLink | None:
    vl = get_version_link_by_version_id(db, version_id)
    if not vl:
        return None
    if vl.index_completed_at is None:
        vl.index_completed_at = datetime.now(timezone.utc)
        db.flush()
    return vl


def clear_version_index_completed(db: Session, version_id: uuid.UUID) -> None:
    vl = get_version_link_by_version_id(db, version_id)
    if vl and vl.index_completed_at is not None:
        vl.index_completed_at = None
        db.flush()


def bind_document_to_indexed_version(
    db: Session,
    *,
    document: Document,
    version: DocumentVersion,
    version_link: RagflowDocumentVersionLink,
) -> RagflowDocumentLink:
    """索引成功后，将文档 canonical 映射指向该成功版本。"""
    return upsert_canonical_link(
        db,
        document=document,
        ragflow_document_id=version_link.ragflow_document_id,
        dataset_id=version_link.dataset_id,
        file_name=version_link.file_name,
        platform_user_id=version_link.platform_user_id,
    )


def resolve_index_link(
    db: Session,
    document: Document,
    *,
    version_id: uuid.UUID | None = None,
) -> tuple[RagflowDocumentVersionLink | None, DocumentVersion | None]:
    """解析用于读切片/检索的版本索引；默认最后索引成功的版本。"""
    version: DocumentVersion | None = None
    if version_id:
        version = db.get(DocumentVersion, version_id)
        if not version or version.document_id != document.id:
            return None, None
    else:
        version = resolve_latest_indexed_version(db, document)
        if not version:
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
    prev_ragflow_id = (vl.ragflow_document_id if vl else None) or None
    if vl:
        if prev_ragflow_id != ragflow_document_id:
            vl.index_completed_at = None
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
