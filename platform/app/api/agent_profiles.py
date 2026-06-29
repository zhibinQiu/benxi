"""系统智能体管理 API — 内置专精智能体列表、运行状态与 Skill 配置。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.agent_profile import AgentProfileDetailOut, AgentProfileOut, AgentProfilePatchIn
from app.schemas.agent_skill import AgentSkillFileContentOut, AgentSkillFileUpdateIn
from app.schemas.common import ApiResponse
from app.services import agent_profile_service as svc
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/admin/agents",
    tags=["admin", "agents"],
    dependencies=[Depends(require_permission("feature.agent_skills"))],
)


@router.get("", response_model=ApiResponse[list[AgentProfileOut]])
def list_agents(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AgentProfileOut]]:
    return ApiResponse(data=svc.list_agent_profiles(db))


@router.get("/{agent_id}", response_model=ApiResponse[AgentProfileDetailOut])
def read_agent(
    agent_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentProfileDetailOut]:
    return ApiResponse(data=svc.get_agent_profile_detail(db, agent_id))


@router.get(
    "/{agent_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def read_agent_file(
    agent_id: str,
    file_path: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentSkillFileContentOut]:
    return ApiResponse(data=svc.get_agent_config_file(db, agent_id, file_path))


@router.put(
    "/{agent_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def update_agent_file(
    agent_id: str,
    file_path: str,
    body: AgentSkillFileUpdateIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillFileContentOut]:
    result = svc.update_agent_config_file(db, agent_id, file_path, body.content)
    write_audit(
        db,
        user_id=user.id,
        action="agent_profile.file_update",
        resource_type="agent_profile",
        detail={"agent_id": agent_id, "path": file_path},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.patch("/{agent_id}", response_model=ApiResponse[AgentProfileOut])
def patch_agent(
    agent_id: str,
    body: AgentProfilePatchIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentProfileOut]:
    result = svc.patch_agent_profile(
        db,
        agent_id,
        enabled=body.enabled,
        service_enabled=body.service_enabled,
        skill_names=body.skill_names,
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_profile.patch",
        resource_type="agent_profile",
        detail={"agent_id": agent_id, **body.model_dump(exclude_unset=True)},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)
