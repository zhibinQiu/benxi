"""数字机器人 API — 对话 + RPA 任务 CRUD + 调度执行。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.digital_robot import (
    DigitalRobotChatRequest,
    DigitalRobotChatResponse,
    DigitalRobotConfirmRequest,
    DigitalRobotConfirmResponse,
    DigitalRobotTaskCreate,
    DigitalRobotTaskUpdate,
    DigitalRobotTaskOut,
)
from app.services.digital_robot_service import (
    chat_with_digital_robot,
    execute_rpa_plan,
    create_task,
    update_task,
    list_tasks,
    get_task,
    delete_task,
    execute_task_now,
)

router = APIRouter(prefix="/digital-robot", tags=["digital-robot"])


# ── 对话 ─────────────────────────────────────────────

@router.post("/chat", response_model=ApiResponse[DigitalRobotChatResponse])
async def digital_robot_chat(
    body: DigitalRobotChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotChatResponse]:
    result = await chat_with_digital_robot(
        db, user, message=body.message, history=body.history, conversation_id=None,
    )
    return ApiResponse(data=DigitalRobotChatResponse.model_validate(result))


@router.post("/confirm", response_model=ApiResponse[DigitalRobotConfirmResponse])
async def digital_robot_confirm(
    body: DigitalRobotConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotConfirmResponse]:
    if body.task_id:
        task = get_task(db, user, body.task_id)
        if not task.plan_json:
            from app.core.exceptions import bad_request as br
            raise br("任务无执行计划")
        from app.schemas.digital_robot import RpaPlan, RpaStep
        plan_data = task.plan_json
        steps = [RpaStep(**s) for s in plan_data.get("steps", [])]
        plan = RpaPlan(steps=steps, summary=plan_data.get("summary", ""), target_url=plan_data.get("target_url", ""))
    elif body.plan:
        plan = body.plan
    else:
        from app.core.exceptions import bad_request as br
        raise br("缺少执行计划")
    result = await execute_rpa_plan(db, user, plan=plan, conversation_id=body.conversation_id)
    return ApiResponse(data=DigitalRobotConfirmResponse.model_validate(result))


# ── 任务 CRUD ────────────────────────────────────────

@router.get("/tasks", response_model=ApiResponse[list[DigitalRobotTaskOut]])
def list_digital_robot_tasks(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status: str = Query("all", description="过滤状态: all/pending/scheduled/running/done/failed/cancelled"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ApiResponse[list[DigitalRobotTaskOut]]:
    rows, total = list_tasks(db, user, status=status, limit=limit, offset=offset)
    return ApiResponse(
        data=[DigitalRobotTaskOut.model_validate(r) for r in rows],
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse[DigitalRobotTaskOut])
def get_digital_robot_task(
    task_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotTaskOut]:
    task = get_task(db, user, task_id)
    return ApiResponse(data=DigitalRobotTaskOut.model_validate(task))


@router.post("/tasks", response_model=ApiResponse[DigitalRobotTaskOut])
def create_digital_robot_task(
    body: DigitalRobotTaskCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotTaskOut]:
    data = body.model_dump(exclude_none=True)
    if body.plan:
        data["plan"] = body.plan.model_dump()
    task = create_task(db, user, data)
    return ApiResponse(data=DigitalRobotTaskOut.model_validate(task))


@router.put("/tasks/{task_id}", response_model=ApiResponse[DigitalRobotTaskOut])
def update_digital_robot_task(
    task_id: str,
    body: DigitalRobotTaskUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotTaskOut]:
    data = body.model_dump(exclude_none=True)
    if body.plan:
        data["plan"] = body.plan.model_dump()
    elif "plan" in data:
        data["plan"] = body.plan  # None
    task = update_task(db, user, task_id, data)
    return ApiResponse(data=DigitalRobotTaskOut.model_validate(task))


@router.delete("/tasks/{task_id}", response_model=ApiResponse[dict])
def delete_digital_robot_task(
    task_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    delete_task(db, user, task_id)
    return ApiResponse(data={"ok": True})


@router.post("/tasks/{task_id}/execute", response_model=ApiResponse[DigitalRobotTaskOut])
def execute_digital_robot_task_now(
    task_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DigitalRobotTaskOut]:
    task = execute_task_now(db, user, task_id)
    return ApiResponse(data=DigitalRobotTaskOut.model_validate(task))
