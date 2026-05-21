from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification


def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str,
    body: str = "",
    link: str | None = None,
) -> Notification:
    n = Notification(user_id=user_id, title=title, body=body, link=link)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def list_notifications(
    db: Session, user_id: uuid.UUID, *, page: int, page_size: int, unread_only: bool
) -> tuple[list[Notification], int]:
    count_stmt = select(func.count()).where(Notification.user_id == user_id)
    if unread_only:
        count_stmt = count_stmt.where(Notification.read_at.is_(None))
    total = db.scalar(count_stmt) or 0
    base = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        base = base.where(Notification.read_at.is_(None))
    items = db.scalars(
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    n = db.get(Notification, notification_id)
    if n and n.user_id == user_id and n.read_at is None:
        from datetime import datetime, timezone

        n.read_at = datetime.now(timezone.utc)
        db.commit()
