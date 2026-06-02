from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.exceptions import bad_request, not_found
from app.database import get_db
from app.models.org import Department, User, UserDepartment
from app.schemas.common import ApiResponse
from app.schemas.org import DepartmentCreate, DepartmentOut, DepartmentUpdate

router = APIRouter(prefix="/departments", tags=["departments"])


def _would_create_parent_cycle(
    db: Session, dept_id: uuid.UUID, parent_id: uuid.UUID
) -> bool:
    """parent 不能为自己或自己的下级。"""
    if parent_id == dept_id:
        return True
    seen: set[uuid.UUID] = set()
    current = db.get(Department, parent_id)
    while current and current.parent_id:
        if current.id in seen:
            break
        seen.add(current.id)
        if current.id == dept_id:
            return True
        current = db.get(Department, current.parent_id)
    return False


@router.get("", response_model=ApiResponse[list[DepartmentOut]])
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        User, Depends(require_any_permission("admin.dept", "admin.user"))
    ],
) -> ApiResponse[list[DepartmentOut]]:
    items = db.scalars(select(Department).order_by(Department.name)).all()
    return ApiResponse(data=[DepartmentOut.model_validate(d) for d in items])


@router.post("", response_model=ApiResponse[DepartmentOut])
def create_department(
    body: DepartmentCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = Department(name=body.name, parent_id=body.parent_id)
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


@router.patch("/{dept_id}", response_model=ApiResponse[DepartmentOut])
def update_department(
    dept_id: uuid.UUID,
    body: DepartmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[DepartmentOut]:
    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("Department not found")
    if body.name is not None:
        dept.name = body.name.strip()
    if "parent_id" in body.model_fields_set:
        parent_id = body.parent_id
        if parent_id is not None:
            parent = db.get(Department, parent_id)
            if not parent:
                raise bad_request("上级部门不存在")
            if _would_create_parent_cycle(db, dept_id, parent_id):
                raise bad_request("上级部门不能为自己或下级部门")
        dept.parent_id = parent_id
    db.commit()
    db.refresh(dept)
    return ApiResponse(data=DepartmentOut.model_validate(dept))


@router.delete("/{dept_id}", response_model=ApiResponse[dict])
def delete_department(
    dept_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.dept"))],
) -> ApiResponse[dict]:
    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("Department not found")
    child = db.scalar(
        select(Department.id).where(Department.parent_id == dept_id).limit(1)
    )
    if child:
        raise bad_request("请先删除或移走下级部门")
    member_count = db.scalar(
        select(UserDepartment.id).where(UserDepartment.dept_id == dept_id).limit(1)
    )
    if member_count:
        raise bad_request("部门下仍有用户，请先在用户管理中调整所属部门")
    db.query(UserDepartment).filter(UserDepartment.dept_id == dept_id).delete()
    db.delete(dept)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(dept_id)})
