from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.scheduled_notification import ScheduledNotification

_logger = logging.getLogger(__name__)

_MAX_SCHEDULE_DELAY_SECONDS = 30 * 24 * 3600  # 30 天


def _db_now(db: Session) -> datetime:
    """从数据库获取当前 UTC 时间，避免系统时钟偏移影响定时通知调度。"""
    try:
        result = db.scalar(func.now())
        if result is not None:
            if isinstance(result, datetime):
                if result.tzinfo is None:
                    result = result.replace(tzinfo=timezone.utc)
                return result
    except Exception:
        _logger.warning("获取数据库时间失败，回退到系统时钟", exc_info=True)
    return datetime.now(timezone.utc)


def _scheduled_max_skew() -> int:
    from app.config import get_settings

    return max(1, int(get_settings().notification_scheduled_max_skew_sec or 5))


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
    local = dt.astimezone()
    if local.second or local.microsecond:
        return local.strftime("%Y-%m-%d %H:%M:%S")
    return local.strftime("%Y-%m-%d %H:%M")


def parse_iso8601(text: str) -> datetime | None:
    """解析 ISO 8601 时间字符串，兼容常见变体。"""
    if not text or not text.strip():
        return None
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    if " " in t and "T" not in t:
        t = t.replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        pass
    if "." in t:
        before, _, after = t.partition(".")
        frac = ""
        tz = ""
        for ch in after:
            if ch in ("+", "-") or (ch == "Z" and not tz):
                idx = after.index(ch)
                tz = after[idx:]
                break
            if ch.isdigit() and len(frac) < 6:
                frac += ch
        t = f"{before}.{frac}{tz}" if frac else before + tz
        try:
            return datetime.fromisoformat(t)
        except ValueError:
            pass
    return None


def parse_relative_delay(text: str) -> timedelta | None:
    """解析相对时间表达式，返回 timedelta。

    支持格式：
      - "8s" / "8秒" / "8秒后"      → 8 秒
      - "5m" / "5分钟" / "5分钟后"    → 5 分钟
      - "2h" / "2小时" / "2小时后"    → 2 小时
      - "1d" / "1天" / "1天后"        → 1 天
    """
    if not text or not text.strip():
        return None
    t = text.strip().lower().replace(" ", "")
    # 去掉尾部"后"
    t = t.rstrip("后")

    patterns: list[tuple[str, Callable[[int], timedelta]]] = [
        (r"^(\d+)\s*s(?:ec(?:onds?)?)?$", lambda v: timedelta(seconds=v)),
        (r"^(\d+)\s*秒$", lambda v: timedelta(seconds=v)),
        (r"^(\d+)\s*m(?:in(?:utes?)?)?$", lambda v: timedelta(minutes=v)),
        (r"^(\d+)\s*分(?:钟)?$", lambda v: timedelta(minutes=v)),
        (r"^(\d+)\s*h(?:ours?)?$", lambda v: timedelta(hours=v)),
        (r"^(\d+)\s*小[时時]$", lambda v: timedelta(hours=v)),
        (r"^(\d+)\s*d(?:ays?)?$", lambda v: timedelta(days=v)),
        (r"^(\d+)\s*天$", lambda v: timedelta(days=v)),
        (r"^(\d+)\s*周$", lambda v: timedelta(weeks=v)),
        (r"^(\d+)\s*w(?:eeks?)?$", lambda v: timedelta(weeks=v)),
    ]
    for regex, factory in patterns:
        match = re.match(regex, t)
        if match:
            try:
                return factory(int(match.group(1)))
            except (ValueError, TypeError):
                return None
    return None


def preview_scheduled_display(
    *,
    scheduled_at: str,
) -> tuple[str, int | None]:
    """将 ISO 8601 时间字符串转为本地时间文案，返回 boost_seconds（轮询加速用）。"""
    try:
        parsed_at = parse_iso8601(str(scheduled_at))
        if parsed_at is None:
            return "", None
        target = _resolve_scheduled_at(scheduled_at=parsed_at)
        display = format_scheduled_at_local(target)
        boost = max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
        return display, boost or None
    except (ValueError, TypeError):
        return "", None


def _resolve_scheduled_at(
    scheduled_at: datetime,
    db: Session | None = None,
) -> datetime:
    now = _db_now(db) if db is not None else datetime.now(timezone.utc)
    target = scheduled_at
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    else:
        target = target.astimezone(timezone.utc)
    # 容忍数秒延迟：AI 处理与代码执行间的微小偏差，以及系统时钟偏移
    skew = _scheduled_max_skew()
    if target <= now - timedelta(seconds=skew):
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
    scheduled_at: datetime,
) -> ScheduledNotification:
    title = (title or "").strip()
    if not title:
        raise ValueError("通知标题不能为空")
    target = _resolve_scheduled_at(scheduled_at=scheduled_at, db=db)
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

    now = _db_now(db)
    countdown = max(0, int((target - now).total_seconds()))
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
        return {"ok": False, "reason": "already_sent"}
    row.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "reason": "cancelled"}


def list_pending_scheduled_notifications(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[ScheduledNotification]:
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
        "notification_id": str(row.id),
        "title": row.title,
        "body": row.body,
        "link": row.link,
        "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def deliver_scheduled_notification(notification_id: uuid.UUID) -> dict[str, Any]:
    """投递一条定时通知（由后台任务调用）。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(ScheduledNotification, notification_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row.cancelled_at is not None:
            return {"ok": False, "reason": "cancelled"}
        if row.sent_at is not None:
            return {"ok": True, "reason": "already_sent"}
        db_now = _db_now(db)
        if row.scheduled_at > db_now + timedelta(seconds=5):
            from app.services.background_job_dispatch import (
                dispatch_scheduled_notification,
            )

            countdown = max(0, int((row.scheduled_at - db_now).total_seconds()))
            dispatch_scheduled_notification(row.id, countdown=countdown)
            return {"ok": True, "reason": "rescheduled", "countdown": countdown}
        create_notification(
            db,
            user_id=row.user_id,
            title=row.title,
            body=row.body,
            link=row.link,
        )
        row.sent_at = db_now
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
        now = _db_now(db)
        # 记录系统时钟与数据库时间的偏差，辅助排查定时通知失效问题
        sys_now = datetime.now(timezone.utc)
        skew = abs((now - sys_now).total_seconds())
        if skew > 2:
            _logger.warning(
                "系统时钟与数据库时间偏差 %.1f 秒，可能影响定时通知调度",
                skew,
            )
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
