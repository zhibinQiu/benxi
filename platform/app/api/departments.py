from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.exceptions import not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.org import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services import department_service

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=ApiResponse[list[DepartmentOut]])
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        User, Depends(require_any_permission("admin.dept", "admin.user"))
    ],
) -> ApiResponse[list[DepartmentOut]]:
    items = department_service.list_departments(db)
    return ApiResponse(data=[DepartmentOut.model_validate(d) for d in items])


@router.post("", response_model=ApiResponse[DepartmentOut])
def create_department(
    body: DepartmentCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = department_service.create_department(
        db, name=body.name, parent_id=body.parent_id
    )
    db.commit()
    db.refresh(dept)
    return ApiResponse(data=DepartmentOut.model_validate(dept))


@router.get("/{dept_id}", response_model=ApiResponse[DepartmentOut])
def get_department(
    dept_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    from app.models.org import Department

    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("Department not found")
    return ApiResponse(data=DepartmentOut.model_validate(dept))


@router.patch("/{dept_id}", response_model=ApiResponse[DepartmentOut])
def update_department(
    dept_id: uuid.UUID,
    body: DepartmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = department_service.update_department(
        db,
        dept_id,
        name=body.name,
        parent_id=body.parent_id,
        parent_id_set="parent_id" in body.model_fields_set,
    )
    db.commit()
    db.refresh(dept)
    return ApiResponse(data=DepartmentOut.model_validate(dept))


@router.delete("/{dept_id}", response_model=ApiResponse[dict])
def delete_department(
    dept_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[dict]:
    department_service.delete_department(db, dept_id)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(dept_id)})
