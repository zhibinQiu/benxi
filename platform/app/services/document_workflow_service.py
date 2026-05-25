"""文档禁止访问管理。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import can_manage_document_denials
from app.core.exceptions import bad_request, forbidden
from app.models.document import Document
from app.models.document_workflow import DocumentAccessDenial
from app.models.org import User


def list_denials(db: Session, document_id: uuid.UUID) -> list[DocumentAccessDenial]:
    return list(
        db.scalars(
            select(DocumentAccessDenial).where(
                DocumentAccessDenial.document_id == document_id
            )
        ).all()
    )


def deny_user_access(
    db: Session,
    actor: User,
    document: Document,
    *,
    user_id: uuid.UUID,
    reason: str = "",
) -> DocumentAccessDenial:
    if not can_manage_document_denials(db, actor, document):
        raise forbidden("无权禁止访问该文档")
    if user_id == document.owner_id:
        raise bad_request("不能禁止文档所有者访问")
    existing = db.scalar(
        select(DocumentAccessDenial).where(
            DocumentAccessDenial.document_id == document.id,
            DocumentAccessDenial.user_id == user_id,
        )
    )
    if existing:
        return existing
    row = DocumentAccessDenial(
        document_id=document.id,
        user_id=user_id,
        reason=reason.strip(),
        created_by=actor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def lift_denial(
    db: Session, actor: User, document: Document, *, user_id: uuid.UUID
) -> None:
    if not can_manage_document_denials(db, actor, document):
        raise forbidden("无权禁止访问该文档")
    row = db.scalar(
        select(DocumentAccessDenial).where(
            DocumentAccessDenial.document_id == document.id,
            DocumentAccessDenial.user_id == user_id,
        )
    )
    if row:
        db.delete(row)
        db.commit()
