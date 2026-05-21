from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.exceptions import bad_request, not_found
from app.core.security import hash_password
from app.database import get_db
from app.models.org import User, UserDepartment, UserRole
from app.schemas.common import ApiResponse
from app.schemas.org import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _user_out(db: Session, user: User) -> UserOut:
    dept_ids = list(
        db.scalars(
            select(UserDepartment.dept_id).where(UserDepartment.user_id == user.id)
        ).all()
    )
    role_ids = list(
        db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)).all()
    )
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        created_at=user.created_at,
        department_ids=dept_ids,
        role_ids=role_ids,
    )


@router.get("", response_model=ApiResponse[list[UserOut]])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[list[UserOut]]:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return ApiResponse(data=[_user_out(db, u) for u in users])


@router.post("", response_model=ApiResponse[UserOut])
def create_user(
    body: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    if db.scalar(select(User).where(User.username == body.username)):
        raise bad_request("Username already exists")
    user = User(
        username=body.username,
        display_name=body.display_name or body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    for i, dept_id in enumerate(body.department_ids):
        db.add(
            UserDepartment(
                user_id=user.id, dept_id=dept_id, is_primary=(i == 0)
            )
        )
    for role_id in body.role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))


@router.patch("/{user_id}", response_model=ApiResponse[UserOut])
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.user"))],
) -> ApiResponse[UserOut]:
    user = db.get(User, user_id)
    if not user:
        raise not_found("User not found")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = body.email
    if body.status is not None:
        user.status = body.status
    if body.department_ids is not None:
        db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete()
        for i, dept_id in enumerate(body.department_ids):
            db.add(
                UserDepartment(
                    user_id=user.id, dept_id=dept_id, is_primary=(i == 0)
                )
            )
    if body.role_ids is not None:
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role_id in body.role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))
