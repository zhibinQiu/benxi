"""本析智能 — 待办与系统通知工具。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.org import User
from app.services import notification_service, todo_service


def list_todos_for_agent(
    db: Session,
    user: User,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in ("pending", "done"):
        raise ValueError("status 须为 pending 或 done")
    items = todo_service.list_todos_for_user(db, user.id, status=status)
    return [todo_service.serialize_todo(t) for t in items]


def create_todo_for_agent(
    db: Session,
    user: User,
    *,
    title: str,
    note: str = "",
) -> dict[str, Any]:
    item = todo_service.create_todo(db, user, title=title, note=note)
    return {
        "message": f"已添加待办：{item.title}",
        "todo": todo_service.serialize_todo(item),
    }


def update_todo_for_agent(
    db: Session,
    user: User,
    *,
    todo_id: uuid.UUID,
    title: str | None = None,
    note: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    item = todo_service.update_todo(
        db,
        user,
        todo_id,
        title=title,
        note=note,
        status=status,
    )
    action = "已完成" if status == "done" else "已更新"
    return {
        "message": f"{action}待办：{item.title}",
        "todo": todo_service.serialize_todo(item),
    }


def delete_todo_for_agent(
    db: Session,
    user: User,
    *,
    todo_id: uuid.UUID,
) -> dict[str, Any]:
    result = todo_service.delete_todo(db, user, todo_id)
    return {"message": "已删除待办", **result}


def send_notification_for_agent(
    db: Session,
    user: User,
    *,
    title: str,
    body: str = "",
    link: str | None = None,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("通知标题不能为空")
    n = notification_service.create_notification(
        db,
        user_id=user.id,
        title=title,
        body=(body or "").strip(),
        link=(link or "").strip() or None,
    )
    return {
        "message": f"已发送系统通知：{title}",
        "notification_id": str(n.id),
    }


def schedule_notification_for_agent(
    db: Session,
    user: User,
    *,
    title: str,
    body: str = "",
    link: str | None = None,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    parsed_at: datetime | None = None
    if scheduled_at:
        text = scheduled_at.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed_at = datetime.fromisoformat(text)
    if parsed_at is None:
        raise ValueError("定时通知须指定 scheduled_at（ISO 8601 格式绝对时间）")
    row = notification_service.schedule_notification(
        db,
        user_id=user.id,
        title=title,
        body=body,
        link=link,
        scheduled_at=parsed_at,
    )
    when = (
        notification_service.format_scheduled_at_local(row.scheduled_at)
        if row.scheduled_at
        else ""
    )
    boost = max(0, int((row.scheduled_at - datetime.now(timezone.utc)).total_seconds()))
    return {
        "message": f"已设置定时通知，将于 {when} 提醒：{row.title}",
        "scheduled": notification_service.serialize_scheduled_notification(row),
        "boost_seconds": boost,
    }


def list_scheduled_notifications_for_agent(
    db: Session,
    user: User,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = notification_service.list_pending_scheduled_notifications(
        db, user.id, limit=limit
    )
    return [notification_service.serialize_scheduled_notification(r) for r in rows]


def cancel_scheduled_notification_for_agent(
    db: Session,
    user: User,
    *,
    notification_id: uuid.UUID,
) -> dict[str, Any]:
    result = notification_service.cancel_scheduled_notification(
        db, user.id, notification_id
    )
    return {"message": "已取消定时通知", **result}
