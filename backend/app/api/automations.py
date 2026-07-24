"""自动化任务 API。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import User
from app.schemas.agent_automation import (
    AutomationCreate,
    AutomationOut,
    AutomationOverviewOut,
    AutomationUpdate,
)
from app.schemas.common import ApiResponse
from app.services import agent_automation_service as svc

router = APIRouter(prefix="/automations", tags=["automations"])


@router.get("/overview", response_model=ApiResponse[AutomationOverviewOut])
def get_overview(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationOverviewOut]:
    return ApiResponse(data=svc.get_overview(db, user.id))


@router.get("", response_model=ApiResponse[list[AutomationOut]])
def list_automations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AutomationOut]]:
    rows = svc.list_automations(db, user.id)
    return ApiResponse(data=[svc.serialize_automation(r) for r in rows])


@router.post("", response_model=ApiResponse[AutomationOut])
def create_automation(
    body: AutomationCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationOut]:
    row = svc.create_automation(db, user, body)
    return ApiResponse(data=svc.serialize_automation(row))


@router.patch("/{automation_id}", response_model=ApiResponse[AutomationOut])
def update_automation(
    automation_id: uuid.UUID,
    body: AutomationUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationOut]:
    row = svc.update_automation(db, user, automation_id, body)
    return ApiResponse(data=svc.serialize_automation(row))


@router.delete("/{automation_id}", response_model=ApiResponse[dict])
def delete_automation(
    automation_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    svc.delete_automation(db, user, automation_id)
    return ApiResponse(data={"ok": True})


@router.post("/{automation_id}/run", response_model=ApiResponse[dict])
async def run_automation_now(
    automation_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    from app.core.exceptions import not_found
    from app.models.agent_automation import AgentAutomation

    row = db.get(AgentAutomation, automation_id)
    if not row or row.user_id != user.id or row.cancelled_at is not None:
        raise not_found("定时任务不存在")
    result = await svc.execute_automation(automation_id, force=True)
    return ApiResponse(data=result)
