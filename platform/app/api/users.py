from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.org import UserCreate, UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=ApiResponse[PageResult[UserOut]])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PageResult[UserOut]]:
    users, total = user_service.list_users_page(db, page=page, page_size=page_size)
    return ApiResponse(
        data=PageResult(
            items=[user_service.serialize_user_out(db, u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[UserOut])
def create_user(
    body: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    user = user_service.create_user_account(db, body)
    db.commit()
    db.refresh(user)
    return ApiResponse(data=user_service.serialize_user_out(db, user))


@router.patch("/{user_id}", response_model=ApiResponse[UserOut])
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    user = db.get(User, user_id)
    if not user:
        from app.core.exceptions import not_found

        raise not_found("User not found")
    user = user_service.update_user_account(db, user, body)
    db.commit()
    db.refresh(user)
    return ApiResponse(data=user_service.serialize_user_out(db, user))


@router.delete("/{user_id}", response_model=ApiResponse[dict])
def delete_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(get_current_user)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[dict]:
    data = user_service.delete_user_by_admin(db, actor=current, target_user_id=user_id)
    db.commit()
    return ApiResponse(data=data)
