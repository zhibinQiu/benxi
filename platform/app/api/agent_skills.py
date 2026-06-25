"""Agent Skills 管理 API — 上传、列表、启停与文件预览。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.agent_profile import AgentProfileDetailOut, AgentProfileOut, AgentProfilePatchIn
from app.schemas.agent_skill import AgentSkillFileContentOut, AgentSkillFileUpdateIn
from app.schemas.agent_skill import (
    AgentMemoryOut,
    AgentMemoryUpdateIn,
    AgentToolOut,
    AgentSkillCatalogItemOut,
    AgentSkillCreateIn,
    AgentSkillDetailOut,
    AgentSkillFileContentOut,
    AgentSkillFileUpdateIn,
    AgentSkillSummaryOut,
    AgentSkillUpdateIn,
    AgentSkillUploadOut,
    BuiltinSkillPatchIn,
    SkillInvokeIn,
    SkillInvokeOut,
    UnifiedSkillOut,
)
from app.schemas.common import ApiResponse, PageResult
from app.services import agent_skill_service as svc
from app.services import agent_profile_service as agent_profile_svc
from app.services import skill_registry_service as registry_svc
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/admin/agent-skills",
    tags=["admin", "agent-skills"],
    dependencies=[Depends(require_permission("feature.agent_skills"))],
)


@router.get("", response_model=ApiResponse[PageResult[AgentSkillSummaryOut]])
def list_agent_skills(
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="按 name / description 搜索"),
    enabled: bool | None = Query(None, description="按启用状态筛选"),
) -> ApiResponse[PageResult[AgentSkillSummaryOut]]:
    return ApiResponse(
        data=svc.list_skills(db, page=page, page_size=page_size, q=q, enabled_only=enabled)
    )


@router.get("/catalog", response_model=ApiResponse[list[AgentSkillCatalogItemOut]])
def read_skill_catalog(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AgentSkillCatalogItemOut]]:
    """轻量目录（内置 + 上传），供智能体 Discovery 阶段使用。"""
    return ApiResponse(data=svc.get_skill_catalog(db, admin_view=True))


@router.get("/registry", response_model=ApiResponse[list[UnifiedSkillOut]])
def read_skill_registry(
    db: Annotated[Session, Depends(get_db)],
    include_disabled: bool = Query(True),
    catalog_only: bool = Query(True),
) -> ApiResponse[list[UnifiedSkillOut]]:
    """Skill 注册表：可对话调用的内置 Skill + 上传包（不含系统功能占位）。"""
    return ApiResponse(
        data=registry_svc.list_unified_skills(
            db, include_disabled=include_disabled, catalog_only=catalog_only
        )
    )


@router.get("/tools", response_model=ApiResponse[list[AgentToolOut]])
def read_agent_tools(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
) -> ApiResponse[list[AgentToolOut]]:
    """平台 Agent 工具目录（只读，不可扩充）。"""
    from app.services.agent_tool_registry import list_agent_tools

    return ApiResponse(data=list_agent_tools(db, user=user))


@router.patch("/builtin/{skill_name}", response_model=ApiResponse[UnifiedSkillOut])
def patch_builtin_skill(
    skill_name: str,
    body: BuiltinSkillPatchIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[UnifiedSkillOut]:
    result = registry_svc.patch_builtin_skill(db, skill_name, enabled=body.enabled)
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.builtin_patch",
        resource_type="agent_skill",
        detail={"name": skill_name, "enabled": body.enabled},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/invoke", response_model=ApiResponse[SkillInvokeOut])
async def invoke_agent_skill(
    body: SkillInvokeIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[SkillInvokeOut]:
    """试调用 skill 工具（管理员调试，后续 agent 循环复用同一 executor）。"""
    result = await registry_svc.invoke_skill(
        db,
        user,
        skill_name=body.skill_name,
        tool_name=body.tool_name,
        params=body.params,
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.invoke",
        resource_type="agent_skill",
        detail={
            "skill_name": body.skill_name,
            "tool_name": body.tool_name,
            "ok": result.ok,
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.get("/agents", response_model=ApiResponse[list[AgentProfileOut]])
def list_system_agents(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AgentProfileOut]]:
    """系统内置专精智能体列表（不可手动创建）。"""
    return ApiResponse(data=agent_profile_svc.list_agent_profiles(db))


@router.get("/agents/{agent_id}", response_model=ApiResponse[AgentProfileDetailOut])
def read_system_agent(
    agent_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentProfileDetailOut]:
    return ApiResponse(data=agent_profile_svc.get_agent_profile_detail(db, agent_id))


@router.get(
    "/agents/{agent_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def read_system_agent_file(
    agent_id: str,
    file_path: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentSkillFileContentOut]:
    return ApiResponse(data=agent_profile_svc.get_agent_config_file(db, agent_id, file_path))


@router.put(
    "/agents/{agent_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def update_system_agent_file(
    agent_id: str,
    file_path: str,
    body: AgentSkillFileUpdateIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillFileContentOut]:
    result = agent_profile_svc.update_agent_config_file(
        db, agent_id, file_path, body.content
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_profile.file_update",
        resource_type="agent_profile",
        detail={"agent_id": agent_id, "path": file_path},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.patch("/agents/{agent_id}", response_model=ApiResponse[AgentProfileOut])
def patch_system_agent(
    agent_id: str,
    body: AgentProfilePatchIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentProfileOut]:
    result = agent_profile_svc.patch_agent_profile(
        db,
        agent_id,
        enabled=body.enabled,
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


@router.get("/{skill_id}", response_model=ApiResponse[AgentSkillDetailOut])
def read_agent_skill(
    skill_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentSkillDetailOut]:
    return ApiResponse(data=svc.get_skill(db, skill_id))


@router.get(
    "/{skill_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def read_agent_skill_file(
    skill_id: uuid.UUID,
    file_path: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AgentSkillFileContentOut]:
    return ApiResponse(data=svc.get_skill_file_content(db, skill_id, file_path))


@router.get("/{skill_id}/download")
def download_agent_skill_zip(
    skill_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """下载已安装 skill 的 ZIP 包（含目录结构，便于备份或迁移）。"""
    data, filename = svc.export_skill_zip(db, skill_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/generate", response_model=ApiResponse[AgentSkillSummaryOut])
def create_generated_agent_skill(
    body: AgentSkillCreateIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillSummaryOut]:
    result = svc.create_generated_skill(
        db,
        user,
        name=body.name,
        description=body.description,
        skill_md_body=body.skill_md_body,
        replace_existing=body.replace_existing,
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.generate",
        resource_type="agent_skill",
        detail={"name": result.name},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.put(
    "/{skill_id}/files/{file_path:path}",
    response_model=ApiResponse[AgentSkillFileContentOut],
)
def update_agent_skill_file(
    skill_id: uuid.UUID,
    file_path: str,
    body: AgentSkillFileUpdateIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillFileContentOut]:
    result = svc.update_skill_file(db, skill_id, file_path, body.content)
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.file_update",
        resource_type="agent_skill",
        detail={"skill_id": str(skill_id), "path": file_path},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/upload/zip", response_model=ApiResponse[AgentSkillUploadOut])
async def upload_agent_skill_zip(
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(..., description="Skill ZIP（含 skill 目录）"),
    replace_existing: bool = Form(True),
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillUploadOut]:
    content = await file.read()
    result = svc.upload_skill_zip(
        db, user, content, replace_existing=replace_existing
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.upload_zip",
        resource_type="agent_skill",
        detail={
            "filename": file.filename,
            "bytes": len(content),
            "skills": [s.name for s in result.skills],
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/upload/folder", response_model=ApiResponse[AgentSkillUploadOut])
async def upload_agent_skill_folder(
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    files: list[UploadFile] = File(..., description="文件夹内各文件的相对路径"),
    paths: Annotated[list[str] | str, Form(...)] = ...,
    replace_existing: bool = Form(True),
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillUploadOut]:
    path_list = paths if isinstance(paths, list) else [paths]
    if len(files) != len(path_list):
        from app.core.exceptions import bad_request

        raise bad_request("files 与 paths 数量不一致")
    entries: list[tuple[str, bytes]] = []
    for upload, rel in zip(files, path_list, strict=True):
        entries.append(((rel or upload.filename or "").strip(), await upload.read()))
    result = svc.upload_skill_folder(
        db, user, entries, replace_existing=replace_existing
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.upload_folder",
        resource_type="agent_skill",
        detail={
            "file_count": len(entries),
            "skills": [s.name for s in result.skills],
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.patch("/{skill_id}", response_model=ApiResponse[AgentSkillSummaryOut])
def patch_agent_skill(
    skill_id: uuid.UUID,
    body: AgentSkillUpdateIn,
    user: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentSkillSummaryOut]:
    result = svc.update_skill(
        db,
        skill_id,
        enabled=body.enabled,
        description=body.description,
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.update",
        resource_type="agent_skill",
        detail={"skill_id": str(skill_id), **body.model_dump(exclude_unset=True)},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.delete("/{skill_id}", response_model=ApiResponse[None])
def delete_agent_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[None]:
    skill = svc.get_skill(db, skill_id)
    svc.delete_skill(db, skill_id)
    write_audit(
        db,
        user_id=user.id,
        action="agent_skill.delete",
        resource_type="agent_skill",
        detail={"skill_id": str(skill_id), "name": skill.name},
        ip_address=client_ip,
    )
    return ApiResponse(data=None)
