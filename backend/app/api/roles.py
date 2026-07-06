from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.exceptions import not_found
from app.database import get_db
from app.models.org import Permission, Role, RolePermission, User
from app.schemas.common import ApiResponse
from app.schemas.org import RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])


def _role_out(db: Session, role: Role) -> RoleOut:
    codes = list(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).all()
    )
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        permission_codes=codes,
    )


@router.get("", response_model=ApiResponse[list[RoleOut]])
def list_roles(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        User, Depends(require_any_permission("admin.role", "admin.user"))
    ],
) -> ApiResponse[list[RoleOut]]:
    roles = db.scalars(select(Role)).all()
    return ApiResponse(data=[_role_out(db, r) for r in roles])


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]


@router.put("/{role_id}/permissions", response_model=ApiResponse[RoleOut])
def set_role_permissions(
    role_id: uuid.UUID,
    body: RolePermissionsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("admin.role"))],
) -> ApiResponse[RoleOut]:
    role = db.get(Role, role_id)
    if not role:
        raise not_found("Role not found")
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for code in body.permission_codes:
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    return ApiResponse(data=_role_out(db, role))
