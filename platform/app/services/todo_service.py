"""待办事项服务 — REST API 与智能体工具共用。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.models.org import User
from app.models.todo import TodoItem


def next_sort_order(db: Session, user_id: uuid.UUID, status: str) -> int:
    row = db.scalar(
        select(TodoItem.sort_order)
        .where(TodoItem.user_id == user_id, TodoItem.status == status)
        .order_by(TodoItem.sort_order.desc())
        .limit(1)
    )
    return (row or -1) + 1


def list_todos_for_user(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[TodoItem]:
    stmt = select(TodoItem).where(TodoItem.user_id == user_id)
    if status in ("pending", "done"):
        stmt = stmt.where(TodoItem.status == status)
    return list(
        db.scalars(
            stmt.order_by(TodoItem.sort_order.asc(), TodoItem.created_at.asc())
        ).all()
    )


def serialize_todo(item: TodoItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "title": item.title,
        "note": item.note,
        "status": item.status,
        "sort_order": item.sort_order,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def create_todo(
    db: Session,
    user: User,
    *,
    title: str,
    note: str = "",
) -> TodoItem:
    title = (title or "").strip()
    if not title:
        raise bad_request("待办标题不能为空")
    item = TodoItem(
        user_id=user.id,
        title=title,
        note=(note or "").strip(),
        status="pending",
        sort_order=next_sort_order(db, user.id, "pending"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_todo(
    db: Session,
    user: User,
    todo_id: uuid.UUID,
    *,
    title: str | None = None,
    note: str | None = None,
    status: str | None = None,
) -> TodoItem:
    item = db.get(TodoItem, todo_id)
    if not item or item.user_id != user.id:
        raise not_found("待办不存在")
    if title is not None:
        title = title.strip()
        if not title:
            raise bad_request("待办标题不能为空")
        item.title = title
    if note is not None:
        item.note = note.strip()
    if status is not None:
        if status not in ("pending", "done"):
            raise bad_request("无效的状态")
        if status != item.status:
            item.status = status
            item.sort_order = next_sort_order(db, user.id, status)
            if status == "done":
                item.completed_at = datetime.now(timezone.utc)
            else:
                item.completed_at = None
    db.commit()
    db.refresh(item)
    return item


def delete_todo(db: Session, user: User, todo_id: uuid.UUID) -> dict[str, Any]:
    item = db.get(TodoItem, todo_id)
    if not item or item.user_id != user.id:
        raise not_found("待办不存在")
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": str(todo_id)}


def batch_create_todos(
    db: Session,
    user: User,
    items: list[dict[str, str]],
) -> list[TodoItem]:
    if not items:
        raise bad_request("至少一条待办")
    base = next_sort_order(db, user.id, "pending")
    created: list[TodoItem] = []
    for i, row in enumerate(items):
        title = str(row.get("title") or "").strip()
        if not title:
            raise bad_request("待办标题不能为空")
        item = TodoItem(
            user_id=user.id,
            title=title,
            note=str(row.get("note") or "").strip(),
            status="pending",
            sort_order=base + i,
        )
        db.add(item)
        created.append(item)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


def replace_pending_todos(
    db: Session,
    user: User,
    items: list[dict[str, str]],
) -> list[TodoItem]:
    pending = list_todos_for_user(db, user.id, status="pending")
    for old in pending:
        db.delete(old)
    db.flush()
    created: list[TodoItem] = []
    for i, row in enumerate(items):
        title = str(row.get("title") or "").strip()
        if not title:
            raise bad_request("待办标题不能为空")
        item = TodoItem(
            user_id=user.id,
            title=title,
            note=str(row.get("note") or "").strip(),
            status="pending",
            sort_order=i,
        )
        db.add(item)
        created.append(item)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


def reorder_todos(
    db: Session,
    user: User,
    *,
    status: str,
    ordered_ids: list[uuid.UUID],
) -> list[TodoItem]:
    if status not in ("pending", "done"):
        raise bad_request("无效的状态")
    items = {
        t.id: t
        for t in db.scalars(
            select(TodoItem).where(
                TodoItem.user_id == user.id, TodoItem.status == status
            )
        ).all()
    }
    if set(ordered_ids) != set(items.keys()):
        raise bad_request("排序列表与当前待办不一致")
    for i, tid in enumerate(ordered_ids):
        items[tid].sort_order = i
    db.commit()
    return list_todos_for_user(db, user.id, status=status)
