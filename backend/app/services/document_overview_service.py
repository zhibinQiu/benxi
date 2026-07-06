"""文档中心概览：按格式统计可修改权限文档数量与已解析数量。"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_format import format_label_display, version_file_format_label
from app.core.permissions import PermissionLevel
from app.models.document import DocumentVersion
from app.models.org import User
from app.services.document_index_service import enrich_document_index_meta, is_index_ready_meta
from app.services.documents.listing import filter_accessible_documents

_UNKNOWN_FORMAT = "unknown"


def collect_document_format_overview(
    db: Session,
    user: User,
    *,
    scope: str | None = None,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> dict:
    """汇总当前分级下、用户拥有可修改权限的文档，按格式统计总数与已解析数。"""
    docs = filter_accessible_documents(
        db,
        user,
        scope=scope,
        dept_id=dept_id,
        owner_id=owner_id,
        min_permission_level=PermissionLevel.modify.value,
    )
    if not docs:
        return {"items": [], "total": 0, "parsed_total": 0}

    version_ids = [d.current_version_id for d in docs if d.current_version_id]
    versions_by_id: dict[uuid.UUID, DocumentVersion] = {}
    if version_ids:
        rows = list(
            db.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            ).all()
        )
        versions_by_id = {row.id: row for row in rows}

    meta_by_doc = enrich_document_index_meta(db, user, docs, live_ragflow=False)

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "parsed": 0})
    for doc in docs:
        fmt = _UNKNOWN_FORMAT
        if doc.current_version_id:
            version = versions_by_id.get(doc.current_version_id)
            if version:
                fmt = version_file_format_label(version.file_name, version.mime_type) or _UNKNOWN_FORMAT
        stats[fmt]["total"] += 1
        if is_index_ready_meta(meta_by_doc.get(str(doc.id))):
            stats[fmt]["parsed"] += 1

    items = sorted(
        [
            {
                "format": fmt,
                "label": format_label_display(None if fmt == _UNKNOWN_FORMAT else fmt),
                "total": counts["total"],
                "parsed": counts["parsed"],
            }
            for fmt, counts in stats.items()
        ],
        key=lambda row: (-row["total"], row["label"]),
    )
    total = sum(row["total"] for row in items)
    parsed_total = sum(row["parsed"] for row in items)
    return {"items": items, "total": total, "parsed_total": parsed_total}
