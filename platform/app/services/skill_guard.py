"""Skill 执行期权限校验 — 文档等资源不得越权。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.models.document import Document
from app.models.org import User


def filter_doc_ids_for_user(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    *,
    level: str = PermissionLevel.query.value,
) -> list[uuid.UUID]:
    """仅保留用户有权访问的文档 ID。"""
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        doc = db.get(Document, doc_id)
        if doc and can_access_document(db, user, doc, level):
            out.append(doc_id)
    return out
