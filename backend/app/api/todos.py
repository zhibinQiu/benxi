from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import User
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
from app.services import todo_service
from app.services.todo_llm_service import llm_adjust_todos, llm_parse_todos

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("", response_model=ApiResponse[list[TodoOut]])
def list_todos(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = Query(default=None, pattern="^(pending|done)$"),
) -> ApiResponse[list[TodoOut]]:
    items = todo_service.list_todos_for_user(db, user.id, status=status)
    return ApiResponse(data=[TodoOut.model_validate(t) for t in items])


@router.post("", response_model=ApiResponse[TodoOut])
def create_todo(
    body: TodoCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TodoOut]:
    item = todo_service.create_todo(
        db, user, title=body.title, note=body.note or "", due_at=body.due_at
    )
    return ApiResponse(data=TodoOut.model_validate(item))


@router.patch("/{todo_id}", response_model=ApiResponse[TodoOut])
def update_todo(
    todo_id: uuid.UUID,
    body: TodoUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TodoOut]:
    item = todo_service.update_todo(
        db,
        user,
        todo_id,
        title=body.title,
        note=body.note,
        status=body.status,
        due_at=body.due_at,
    )
    return ApiResponse(data=TodoOut.model_validate(item))


@router.post("/reorder", response_model=ApiResponse[list[TodoOut]])
def reorder_todos(
    body: TodoReorder,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[TodoOut]]:
    ordered = todo_service.reorder_todos(
        db, user, status=body.status, ordered_ids=body.ordered_ids
    )
    return ApiResponse(data=[TodoOut.model_validate(t) for t in ordered])


@router.delete("/{todo_id}", response_model=ApiResponse[dict])
def delete_todo(
    todo_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    data = todo_service.delete_todo(db, user, todo_id)
    return ApiResponse(data=data)


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
    pending = todo_service.list_todos_for_user(db, user.id, status="pending")
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
    created = todo_service.batch_create_todos(
        db,
        user,
        [
            {"title": row.title, "note": row.note or "", "due_at": row.due_at}
            for row in body.items
        ],
    )
    return ApiResponse(data=[TodoOut.model_validate(t) for t in created])


@router.put("/pending/replace", response_model=ApiResponse[list[TodoOut]])
def replace_pending_todos(
    body: TodoBatchCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[TodoOut]]:
    created = todo_service.replace_pending_todos(
        db,
        user,
        [
            {"title": row.title, "note": row.note or "", "due_at": row.due_at}
            for row in body.items
        ],
    )
    return ApiResponse(data=[TodoOut.model_validate(t) for t in created])
