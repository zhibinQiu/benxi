"""AIP Secret Key 管理 API（管理员）。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.aip_secret_key import (
    AipSecretKeyCreateIn,
    AipSecretKeyCreatedOut,
    AipSecretKeyOut,
)
from app.schemas.common import ApiResponse
from app.services import aip_secret_key_service as sk_svc
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/admin/aip/keys",
    tags=["admin", "aip"],
    dependencies=[Depends(require_permission("feature.agent_skills"))],
)


@router.get("", response_model=ApiResponse[list[AipSecretKeyOut]])
def list_aip_keys(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AipSecretKeyOut]]:
    return ApiResponse(data=sk_svc.list_secret_keys(db))


@router.post("", response_model=ApiResponse[AipSecretKeyCreatedOut])
def create_aip_key(
    body: AipSecretKeyCreateIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipSecretKeyCreatedOut]:
    result = sk_svc.create_secret_key(db, user, body.purpose)
    write_audit(
        db,
        user_id=user.id,
        action="aip_secret_key.create",
        resource_type="aip_secret_key",
        detail={"id": str(result.id), "purpose": result.purpose, "prefix": result.key_prefix},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.delete("/{key_id}", response_model=ApiResponse[dict])
def delete_aip_key(
    key_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[dict]:
    sk_svc.delete_secret_key(db, key_id)
    write_audit(
        db,
        user_id=user.id,
        action="aip_secret_key.delete",
        resource_type="aip_secret_key",
        detail={"id": str(key_id)},
        ip_address=client_ip,
    )
    return ApiResponse(data={"deleted": True})
