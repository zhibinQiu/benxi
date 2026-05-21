from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.exceptions import not_found
from app.database import get_db
from app.models.org import Department, User
from app.schemas.common import ApiResponse
from app.schemas.org import DepartmentCreate, DepartmentOut

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=ApiResponse[list[DepartmentOut]])
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[list[DepartmentOut]]:
    items = db.scalars(select(Department).order_by(Department.sort_order)).all()
    return ApiResponse(data=[DepartmentOut.model_validate(d) for d in items])


@router.post("", response_model=ApiResponse[DepartmentOut])
def create_department(
    body: DepartmentCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = Department(
        name=body.name, parent_id=body.parent_id, sort_order=body.sort_order
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return ApiResponse(data=DepartmentOut.model_validate(dept))


@router.get("/{dept_id}", response_model=ApiResponse[DepartmentOut])
def get_department(
    dept_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("Department not found")
    return ApiResponse(data=DepartmentOut.model_validate(dept))
