from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
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
        n.read_at = datetime.now(timezone.utc)
        db.commit()


def mark_all_read(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    """将全部未读标为已读，并清除该用户全部通知。"""
    unread = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id)
        )
        or 0
    )
    if total:
        db.execute(delete(Notification).where(Notification.user_id == user_id))
        db.commit()
    return {"updated": int(unread), "deleted": int(total)}
