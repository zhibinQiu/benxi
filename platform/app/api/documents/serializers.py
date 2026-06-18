"""文档 API 路由共用的序列化与辅助逻辑。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.document_scope import (
    can_modify_document,
    can_query_document,
    can_read_document,
)
from app.domains.knowledge import knowledge
from app.models.document import Document, DocumentLibraryFolder, DocumentVersion, PermissionLevel
from app.models.org import Department, User
from app.schemas.document import DocumentDetail, DocumentListItem, DocumentVersionOut
from app.services import document_service

logger = logging.getLogger(__name__)


def sync_kb_grants_if_enabled(db: Session, doc: Document) -> None:
    if not get_settings().knowflow_enabled:
        return
    try:
        knowledge.sync_kb_grants(db, doc)
    except Exception:
        logger.warning("同步知识库授权失败 doc=%s", doc.id, exc_info=True)


def owner_display(db: Session, owner_id: uuid.UUID) -> str:
    from app.core.user_display import user_display_name

    return user_display_name(db.get(User, owner_id))


def dept_display(db: Session, dept_id: uuid.UUID | None) -> str | None:
    if not dept_id:
        return None
    dept = db.get(Department, dept_id)
    if not dept:
        return None
    return (dept.name or "").strip() or None


def batch_owner_names(db: Session, owner_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """批量解析文档所有者显示名，避免列表 N+1。"""
    from app.core.user_display import user_display_name

    if not owner_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(owner_ids))).all()
    return {u.id: user_display_name(u) for u in users}


def batch_dept_names(db: Session, dept_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not dept_ids:
        return {}
    rows = db.scalars(select(Department).where(Department.id.in_(dept_ids))).all()
    return {
        d.id: (d.name or "").strip() or ""
        for d in rows
        if (d.name or "").strip()
    }


def batch_uploaded_at(db: Session, docs: list[Document]) -> dict[uuid.UUID, datetime]:
    """批量计算 uploaded_at：优先当前版本时间，否则首版或文档创建时间。"""
    if not docs:
        return {}
    doc_ids = [d.id for d in docs]
    current_vids = {d.id: d.current_version_id for d in docs if d.current_version_id}
    current_times: dict[uuid.UUID, datetime] = {}
    if current_vids:
        versions = db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.id.in_(set(current_vids.values()))
            )
        ).all()
        ver_time = {v.id: v.created_at for v in versions}
        for doc_id, vid in current_vids.items():
            if vid in ver_time:
                current_times[doc_id] = ver_time[vid]

    first_rows = db.execute(
        select(
            DocumentVersion.document_id,
            func.min(DocumentVersion.created_at),
        )
        .where(DocumentVersion.document_id.in_(doc_ids))
        .group_by(DocumentVersion.document_id)
    ).all()
    first_times = {row[0]: row[1] for row in first_rows}

    out: dict[uuid.UUID, datetime] = {}
    for d in docs:
        if d.id in current_times:
            out[d.id] = current_times[d.id]
        elif d.id in first_times:
            out[d.id] = first_times[d.id]
        else:
            out[d.id] = d.created_at
    return out


def uploaded_at(db: Session, doc: Document) -> datetime | None:
    return batch_uploaded_at(db, [doc]).get(doc.id)


def _effective_level(
    can_modify: bool,
    can_query: bool,
    can_read: bool,
) -> str | None:
    if can_modify:
        return PermissionLevel.modify.value
    if can_query:
        return PermissionLevel.query.value
    if can_read:
        return PermissionLevel.visible.value
    return None


def version_out(
    db: Session,
    doc: Document,
    version: DocumentVersion,
    *,
    user: User | None = None,
    index_meta: dict | None = None,
) -> DocumentVersionOut:
    from app.services.document_index_service import apply_index_meta_to_item

    uploaded = document_service.is_version_uploaded(version)
    base = DocumentVersionOut.model_validate(version)
    row = base.model_copy(
        update={
            "uploaded": uploaded,
            "is_current": version.id == doc.current_version_id,
            "file_name": version.file_name or "",
        }
    )
    if user is not None and index_meta is not None:
        row = apply_index_meta_to_item(row, index_meta.get(str(version.id)))
    return row


def folder_name(db: Session, folder_id: uuid.UUID | None) -> str | None:
    if not folder_id:
        return None
    folder = db.get(DocumentLibraryFolder, folder_id)
    return (folder.name or "").strip() or None if folder else None


def document_detail(
    db: Session,
    doc: Document,
    *,
    user: User | None = None,
    live_index: bool | None = None,
) -> DocumentDetail:
    from app.config import get_settings
    from app.services.document_index_service import (
        apply_index_meta_to_item,
        enrich_document_index_meta,
        enrich_version_index_meta,
    )

    if live_index is None:
        live_index = get_settings().knowledge_detail_live_index_meta

    document_service.resolve_current_version(db, doc)
    db.refresh(doc)
    can_modify = can_modify_document(db, user, doc) if user else False
    version_rows = document_service.list_document_versions(db, doc.id)
    version_meta = (
        enrich_version_index_meta(
            db, user, version_rows, live_ragflow=live_index
        )
        if user
        else {}
    )
    detail = DocumentDetail(
        id=doc.id,
        title=doc.title,
        status=doc.status,
        scope=doc.scope,
        folder_id=doc.folder_id,
        folder_name=folder_name(db, doc.folder_id),
        owner_id=doc.owner_id,
        owner_name=owner_display(db, doc.owner_id),
        dept_id=doc.dept_id,
        dept_name=dept_display(db, doc.dept_id),
        current_version_id=doc.current_version_id,
        description=doc.description,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        uploaded_at=uploaded_at(db, doc),
        deleted_at=doc.deleted_at,
        can_modify=can_modify,
        can_edit=can_modify,
        can_delete=can_modify,
        versions=[
            version_out(db, doc, v, user=user, index_meta=version_meta)
            for v in version_rows
        ],
    )
    if user is not None:
        meta = enrich_document_index_meta(
            db, user, [doc], live_ragflow=live_index
        ).get(str(doc.id))
        detail = apply_index_meta_to_item(detail, meta)
    return detail


def attach_folder_names(
    db: Session, items: list[DocumentListItem]
) -> list[DocumentListItem]:
    folder_ids = {i.folder_id for i in items if i.folder_id}
    names: dict[uuid.UUID, str] = {}
    if folder_ids:
        for row in db.scalars(
            select(DocumentLibraryFolder).where(
                DocumentLibraryFolder.id.in_(folder_ids)
            )
        ).all():
            names[row.id] = row.name
    return [
        item.model_copy(
            update={"folder_name": names.get(item.folder_id) if item.folder_id else None}
        )
        for item in items
    ]


def current_version_formats(
    db: Session, docs: list[Document]
) -> dict[uuid.UUID, str | None]:
    from app.core.document_format import version_file_format_label

    version_ids = [d.current_version_id for d in docs if d.current_version_id]
    if not version_ids:
        return {}
    rows = db.scalars(
        select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
    ).all()
    return {
        v.id: version_file_format_label(v.file_name, v.mime_type) for v in rows
    }


def list_items_with_owners(
    db: Session,
    docs: list[Document],
    *,
    include_owner_name: bool,
    user: User | None = None,
) -> list[DocumentListItem]:
    from app.services.document_index_service import (
        apply_index_meta_to_item,
        enrich_document_index_meta,
    )

    fmt_by_ver = current_version_formats(db, docs)
    uploaded_map = batch_uploaded_at(db, docs)
    owner_names = (
        batch_owner_names(db, {d.owner_id for d in docs})
        if include_owner_name
        else {}
    )
    dept_ids = {d.dept_id for d in docs if d.dept_id}
    dept_names = batch_dept_names(db, dept_ids) if dept_ids else {}
    index_meta = (
        enrich_document_index_meta(db, user, docs) if user else {}
    )
    out: list[DocumentListItem] = []
    for d in docs:
        item = DocumentListItem.model_validate(d)
        extra: dict = {"uploaded_at": uploaded_map.get(d.id)}
        if d.current_version_id and d.current_version_id in fmt_by_ver:
            extra["file_format"] = fmt_by_ver[d.current_version_id]
        if include_owner_name:
            extra["owner_name"] = owner_names.get(d.owner_id)
        if d.dept_id:
            extra["dept_name"] = dept_names.get(d.dept_id)
        if user is not None:
            can_mod = can_modify_document(db, user, d)
            can_q = can_query_document(db, user, d)
            can_r = can_read_document(db, user, d)
            extra["can_modify"] = can_mod
            extra["can_edit"] = can_mod
            extra["can_delete"] = can_mod
            extra["effective_level"] = _effective_level(can_mod, can_q, can_r)
        item = item.model_copy(update=extra)
        if user is not None:
            item = apply_index_meta_to_item(item, index_meta.get(str(d.id)))
        out.append(item)
    return out


def attachment_disposition(file_name: str) -> str:
    name = (file_name or "download").replace("\n", "").replace("\r", "")
    ascii_name = "".join(
        c if ord(c) < 128 and c not in ('"', "\\") else "_" for c in name
    ).strip() or "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(name)}"
    )


def inline_disposition(file_name: str) -> str:
    name = (file_name or "preview").replace("\n", "").replace("\r", "")
    return f"inline; filename*=UTF-8''{quote(name)}"
