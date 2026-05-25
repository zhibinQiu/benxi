from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import bad_request, not_found
from app.database import get_db
from app.models.org import User
from app.models.todo import TodoItem
from app.schemas.common import ApiResponse
from app.schemas.todo import (
    TodoBatchCreate,
    TodoCreate,
    TodoLlmRequest,
    TodoLlmResponse,
    TodoOut,
    TodoReorder,
    TodoUpdate,
)
from app.services.todo_llm_service import llm_adjust_todos, llm_parse_todos

router = APIRouter(prefix="/todos", tags=["todos"])


def _next_sort_order(db: Session, user_id: uuid.UUID, status: str) -> int:
    row = db.scalar(
        select(TodoItem.sort_order)
        .where(TodoItem.user_id == user_id, TodoItem.status == status)
        .order_by(TodoItem.sort_order.desc())
        .limit(1)
    )
    return (row or -1) + 1


def _list_for_user(
    db: Session, user_id: uuid.UUID, status: str | None
) -> list[TodoItem]:
    stmt = select(TodoItem).where(TodoItem.user_id == user_id)
    if status in ("pending", "done"):
        stmt = stmt.where(TodoItem.status == status)
    return list(
        db.scalars(stmt.order_by(TodoItem.sort_order.asc(), TodoItem.created_at.asc())).all()
    )


@router.get("", response_model=ApiResponse[list[TodoOut]])
def list_todos(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = Query(default=None, pattern="^(pending|done)$"),
) -> ApiResponse[list[TodoOut]]:
    items = _list_for_user(db, user.id, status)
    return ApiResponse(data=[TodoOut.model_validate(t) for t in items])


@router.post("", response_model=ApiResponse[TodoOut])
def create_todo(
    body: TodoCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TodoOut]:
    item = TodoItem(
        user_id=user.id,
        title=body.title.strip(),
        note=(body.note or "").strip(),
        status="pending",
        sort_order=_next_sort_order(db, user.id, "pending"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ApiResponse(data=TodoOut.model_validate(item))


@router.patch("/{todo_id}", response_model=ApiResponse[TodoOut])
def update_todo(
    todo_id: uuid.UUID,
    body: TodoUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TodoOut]:
    item = db.get(TodoItem, todo_id)
    if not item or item.user_id != user.id:
        raise not_found("Todo not found")
    if body.title is not None:
        item.title = body.title.strip()
    if body.note is not None:
        item.note = body.note.strip()
    if body.status is not None:
        if body.status not in ("pending", "done"):
            raise bad_request("Invalid status")
        if body.status != item.status:
            item.status = body.status
            item.sort_order = _next_sort_order(db, user.id, body.status)
            if body.status == "done":
                item.completed_at = datetime.now(timezone.utc)
            else:
                item.completed_at = None
    db.commit()
    db.refresh(item)
    return ApiResponse(data=TodoOut.model_validate(item))


@router.post("/reorder", response_model=ApiResponse[list[TodoOut]])
def reorder_todos(
    body: TodoReorder,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[TodoOut]]:
    if body.status not in ("pending", "done"):
        raise bad_request("Invalid status")
    items = {
        t.id: t
        for t in db.scalars(
            select(TodoItem).where(
                TodoItem.user_id == user.id, TodoItem.status == body.status
            )
        ).all()
    }
    if set(body.ordered_ids) != set(items.keys()):
        raise bad_request("排序列表与当前待办不一致")
    for i, tid in enumerate(body.ordered_ids):
        items[tid].sort_order = i
    db.commit()
    ordered = _list_for_user(db, user.id, body.status)
    return ApiResponse(data=[TodoOut.model_validate(t) for t in ordered])


@router.delete("/{todo_id}", response_model=ApiResponse[dict])
def delete_todo(
    todo_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    item = db.get(TodoItem, todo_id)
    if not item or item.user_id != user.id:
        raise not_found("Todo not found")
    db.delete(item)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(todo_id)})


@router.post("/llm", response_model=ApiResponse[TodoLlmResponse])
async def todo_llm(
    body: TodoLlmRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TodoLlmResponse]:
    if body.mode == "parse":
        items = await llm_parse_todos(body.text)
        return ApiResponse(
            data=TodoLlmResponse(
                mode="parse",
                items=items,
                message=f"已解析 {len(items)} 条待办",
            )
        )
    pending = _list_for_user(db, user.id, "pending")
    parsed = await llm_adjust_todos(
        body.text,
        [{"title": t.title, "note": t.note} for t in pending],
    )
    return ApiResponse(
        data=TodoLlmResponse(
            mode="adjust",
            items=parsed,
            message=f"建议待办列表共 {len(parsed)} 条，确认后将替换当前待办",
        )
    )


@router.post("/batch", response_model=ApiResponse[list[TodoOut]])
def batch_create_todos(
    body: TodoBatchCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[TodoOut]]:
    base = _next_sort_order(db, user.id, "pending")
    created: list[TodoItem] = []
    for i, row in enumerate(body.items):
        item = TodoItem(
            user_id=user.id,
            title=row.title.strip(),
            note=(row.note or "").strip(),
            status="pending",
            sort_order=base + i,
        )
        db.add(item)
        created.append(item)
    db.commit()
    for c in created:
        db.refresh(c)
    return ApiResponse(data=[TodoOut.model_validate(t) for t in created])


@router.put("/pending/replace", response_model=ApiResponse[list[TodoOut]])
def replace_pending_todos(
    body: TodoBatchCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[TodoOut]]:
    pending = _list_for_user(db, user.id, "pending")
    for old in pending:
        db.delete(old)
    db.flush()
    created: list[TodoItem] = []
    for i, row in enumerate(body.items):
        item = TodoItem(
            user_id=user.id,
            title=row.title.strip(),
            note=(row.note or "").strip(),
            status="pending",
            sort_order=i,
        )
        db.add(item)
        created.append(item)
    db.commit()
    for c in created:
        db.refresh(c)
    return ApiResponse(data=[TodoOut.model_validate(t) for t in created])
