from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.scheduled_notification import ScheduledNotification

_logger = logging.getLogger(__name__)

_MAX_SCHEDULE_DELAY_SECONDS = 30 * 24 * 3600  # 30 天


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


def format_scheduled_at_local(dt: datetime) -> str:
    """用户可见的本地提醒时间；含非零秒时展示到秒。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    if local.second or local.microsecond:
        return local.strftime("%Y-%m-%d %H:%M:%S")
    return local.strftime("%Y-%m-%d %H:%M")


def preview_scheduled_display(
    *,
    delay_seconds: int | None = None,
    delay_minutes: int | None = None,
    scheduled_at: datetime | str | None = None,
) -> tuple[str, int | None]:
    """将定时参数转为本地时间文案，并返回 boost_seconds（轮询加速用）。"""
    try:
        parsed_at: datetime | None = None
        if scheduled_at is not None:
            text = str(scheduled_at).strip()
            if text:
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                parsed_at = datetime.fromisoformat(text)
        target = _resolve_scheduled_at(
            delay_seconds=delay_seconds,
            delay_minutes=delay_minutes,
            scheduled_at=parsed_at,
        )
        display = format_scheduled_at_local(target)
        boost = max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
        return display, boost or None
    except (ValueError, TypeError):
        return "", None


def _resolve_scheduled_at(
    *,
    delay_seconds: int | None = None,
    delay_minutes: int | None = None,
    scheduled_at: datetime | None = None,
) -> datetime:
    now = datetime.now(timezone.utc)
    if scheduled_at is not None:
        target = scheduled_at
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        else:
            target = target.astimezone(timezone.utc)
    else:
        seconds = 0
        if delay_seconds is not None:
            seconds = int(delay_seconds)
        elif delay_minutes is not None:
            seconds = int(delay_minutes) * 60
        if seconds <= 0:
            raise ValueError("定时通知须指定正数的 delay_minutes 或 delay_seconds")
        target = now + timedelta(seconds=seconds)
    if target <= now:
        raise ValueError("通知时间须晚于当前时刻")
    delta = (target - now).total_seconds()
    if delta > _MAX_SCHEDULE_DELAY_SECONDS:
        raise ValueError("定时通知最远不得超过 30 天")
    return target


def schedule_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str,
    body: str = "",
    link: str | None = None,
    delay_seconds: int | None = None,
    delay_minutes: int | None = None,
    scheduled_at: datetime | None = None,
) -> ScheduledNotification:
    title = (title or "").strip()
    if not title:
        raise ValueError("通知标题不能为空")
    target = _resolve_scheduled_at(
        delay_seconds=delay_seconds,
        delay_minutes=delay_minutes,
        scheduled_at=scheduled_at,
    )
    row = ScheduledNotification(
        user_id=user_id,
        title=title,
        body=(body or "").strip(),
        link=(link or "").strip() or None,
        scheduled_at=target,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    from app.services.background_job_dispatch import dispatch_scheduled_notification

    countdown = max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
    dispatch_scheduled_notification(row.id, countdown=countdown)
    return row


def cancel_scheduled_notification(
    db: Session,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> dict[str, Any]:
    row = db.get(ScheduledNotification, notification_id)
    if not row or row.user_id != user_id:
        raise ValueError("定时通知不存在")
    if row.sent_at is not None:
        raise ValueError("通知已发送，无法取消")
    if row.cancelled_at is not None:
        return {"cancelled": True, "id": str(notification_id), "already": True}
    row.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return {"cancelled": True, "id": str(notification_id)}


def list_pending_scheduled_notifications(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[ScheduledNotification]:
    limit = max(1, min(int(limit or 20), 50))
    return list(
        db.scalars(
            select(ScheduledNotification)
            .where(
                ScheduledNotification.user_id == user_id,
                ScheduledNotification.sent_at.is_(None),
                ScheduledNotification.cancelled_at.is_(None),
            )
            .order_by(ScheduledNotification.scheduled_at.asc())
            .limit(limit)
        ).all()
    )


def serialize_scheduled_notification(row: ScheduledNotification) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "body": row.body,
        "link": row.link,
        "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
    }


def deliver_scheduled_notification(notification_id: uuid.UUID) -> dict[str, Any]:
    """投递一条定时通知（由后台任务调用）。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # 行锁保证进程内 Timer 与 Celery 并发投递时只生成一条用户通知
        row = db.scalar(
            select(ScheduledNotification)
            .where(ScheduledNotification.id == notification_id)
            .with_for_update()
        )
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row.cancelled_at is not None:
            return {"ok": False, "reason": "cancelled"}
        if row.sent_at is not None:
            return {"ok": True, "reason": "already_sent"}
        now = datetime.now(timezone.utc)
        if row.scheduled_at > now + timedelta(seconds=5):
            # 进程重启后可能提前触发，重新调度
            from app.services.background_job_dispatch import (
                dispatch_scheduled_notification,
            )

            countdown = max(0, int((row.scheduled_at - now).total_seconds()))
            dispatch_scheduled_notification(row.id, countdown=countdown)
            return {"ok": True, "reason": "rescheduled", "countdown": countdown}
        create_notification(
            db,
            user_id=row.user_id,
            title=row.title,
            body=row.body,
            link=row.link,
        )
        row.sent_at = now
        db.commit()
        return {"ok": True, "reason": "delivered"}
    except Exception:
        db.rollback()
        _logger.exception("投递定时通知失败 id=%s", notification_id)
        raise
    finally:
        db.close()


def recover_pending_scheduled_notifications() -> int:
    """启动时恢复未投递的定时通知。"""
    from app.database import SessionLocal

    db = SessionLocal()
    recovered = 0
    try:
        now = datetime.now(timezone.utc)
        rows = list(
            db.scalars(
                select(ScheduledNotification).where(
                    ScheduledNotification.sent_at.is_(None),
                    ScheduledNotification.cancelled_at.is_(None),
                    ScheduledNotification.scheduled_at > now - timedelta(days=30),
                )
            ).all()
        )
        from app.services.background_job_dispatch import dispatch_scheduled_notification

        for row in rows:
            countdown = max(0, int((row.scheduled_at - now).total_seconds()))
            dispatch_scheduled_notification(row.id, countdown=countdown)
            recovered += 1
        if recovered:
            _logger.info("已恢复 %s 条待投递定时通知", recovered)
        return recovered
    finally:
        db.close()
