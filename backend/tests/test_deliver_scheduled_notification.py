"""定时通知投递幂等性。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.notification import Notification
from app.models.org import User
from app.models.scheduled_notification import ScheduledNotification
from app.services.notification_service import deliver_scheduled_notification


def _bootstrap_user(db):
    return db.scalar(select(User).where(User.phone == bootstrap_login_id()))


def test_deliver_scheduled_notification_is_idempotent():
    db = SessionLocal()
    try:
        user = _bootstrap_user(db)
        assert user is not None
        scheduled = ScheduledNotification(
            user_id=user.id,
            title="喝水提醒",
            body="该喝水了",
            scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(scheduled)
        db.commit()
        db.refresh(scheduled)

        first = deliver_scheduled_notification(scheduled.id)
        second = deliver_scheduled_notification(scheduled.id)

        assert first["reason"] == "delivered"
        assert second["reason"] == "already_sent"
        count = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.title == "喝水提醒",
            )
        )
        assert count == 1
    finally:
        db.close()
