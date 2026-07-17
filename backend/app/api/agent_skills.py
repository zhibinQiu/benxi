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
from app.schemas.agent_profile import (
    AgentProfileDetailOut,
    AgentProfileOut,
    AgentProfilePatchIn,
    KnowledgeMountCreateIn,
)
from app.schemas.aip_external_agent import (
    AipExternalAgentCreateIn,
    AipExternalAgentOut,
    AipExternalAgentPatchIn,
)
from app.schemas.mcp_external_skill import (
    McpExternalSkillCreateIn,
    McpExternalSkillOut,
    McpExternalSkillPatchIn,
)
from app.schemas.agent_skill import (
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
    RoutingCatalogOut,
    SkillInvokeIn,
    SkillInvokeOut,
    UnifiedSkillOut,
)
from app.schemas.common import ApiResponse, PageResult
from app.services import agent_skill_service as svc
from app.services import agent_profile_service as agent_profile_svc
from app.services import aip_external_agent_service as ext_agent_svc
from app.services import mcp_external_skill_service as mcp_skill_svc
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


@router.get("/routing/skills.md", response_model=ApiResponse[RoutingCatalogOut])
def read_routing_skills_catalog(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[RoutingCatalogOut]:
    """调度用 skills.md 路由目录（只读；发展技能段随上传包自动更新）。"""
    from app.core.routing_catalog_md import build_skills_routing_display

    return ApiResponse(
        data=RoutingCatalogOut(
            path="skills.md",
            text=build_skills_routing_display(db),
        )
    )


@router.get("/routing/agents.md", response_model=ApiResponse[RoutingCatalogOut])
def read_routing_agents_catalog() -> ApiResponse[RoutingCatalogOut]:
    """调度用 agents.md 路由目录（只读；随后台版本更新）。"""
    from app.core.routing_catalog_md import build_agents_routing_display

    return ApiResponse(
        data=RoutingCatalogOut(
            path="agents.md",
            text=build_agents_routing_display(),
        )
    )


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
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
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
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AgentProfileOut]:
    result = agent_profile_svc.patch_agent_profile(
        db,
        agent_id,
        enabled=body.enabled,
        service_enabled=body.service_enabled,
        skill_names=body.skill_names,
        runtime_tool_names=body.runtime_tool_names,
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


@router.get(
    "/external",
    response_model=ApiResponse[list[AipExternalAgentOut]],
    include_in_schema=False,
)
@router.get("/external-agents", response_model=ApiResponse[list[AipExternalAgentOut]])
def list_external_agents_for_ui(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AipExternalAgentOut]]:
    from app.core.aip.external_registry import load_config_external_agents

    db_items = ext_agent_svc.list_external_agents_admin(db)
    db_aids = {item.aid for item in db_items}
    config_items = [
        AipExternalAgentOut(
            id=None,
            aid=record.aid,
            name=record.name,
            description=record.description,
            service_endpoint=record.service_endpoint,
            enabled=record.enabled,
            source="config",
        )
        for record in load_config_external_agents()
        if record.aid not in db_aids
    ]
    return ApiResponse(data=[*db_items, *config_items])


@router.post(
    "/external",
    response_model=ApiResponse[AipExternalAgentOut],
    include_in_schema=False,
)
@router.post("/external-agents", response_model=ApiResponse[AipExternalAgentOut])
def create_external_agent_for_ui(
    body: AipExternalAgentCreateIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipExternalAgentOut]:
    result = ext_agent_svc.create_external_agent(db, body)
    write_audit(
        db,
        user_id=user.id,
        action="aip_external_agent.create",
        resource_type="aip_external_agent",
        detail={"id": str(result.id), "aid": result.aid},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.patch("/external-agents/{agent_id}", response_model=ApiResponse[AipExternalAgentOut])
def patch_external_agent_for_ui(
    agent_id: uuid.UUID,
    body: AipExternalAgentPatchIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AipExternalAgentOut]:
    result = ext_agent_svc.patch_external_agent(db, agent_id, body)
    write_audit(
        db,
        user_id=user.id,
        action="aip_external_agent.patch",
        resource_type="aip_external_agent",
        detail={"id": str(agent_id), **body.model_dump(exclude_unset=True)},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.delete("/external-agents/{agent_id}", response_model=ApiResponse[dict])
def delete_external_agent_for_ui(
    agent_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[dict]:
    ext_agent_svc.delete_external_agent(db, agent_id)
    write_audit(
        db,
        user_id=user.id,
        action="aip_external_agent.delete",
        resource_type="aip_external_agent",
        detail={"id": str(agent_id)},
        ip_address=client_ip,
    )
    return ApiResponse(data={"deleted": True})


@router.get("/mcp-skills", response_model=ApiResponse[list[McpExternalSkillOut]])
def list_mcp_skills_for_ui(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[McpExternalSkillOut]]:
    from app.core.mcp.external_registry import load_config_mcp_skills
    from app.schemas.mcp_external_skill import McpToolOut

    db_items = mcp_skill_svc.list_mcp_skills_admin(db)
    db_names = {item.name for item in db_items}
    config_items = [
        McpExternalSkillOut(
            id=None,
            name=record.name,
            title=record.title,
            description=record.description,
            endpoint=record.endpoint,
            transport=record.transport,
            enabled=record.enabled,
            tools=[
                McpToolOut(
                    name=str(tool.get("name") or ""),
                    description=str(tool.get("description") or ""),
                    inputSchema=tool.get("inputSchema")
                    if isinstance(tool.get("inputSchema"), dict)
                    else {},
                )
                for tool in record.tools_cache
            ],
            use_when=record.use_when,
            dont_use_when=record.dont_use_when,
            output=record.output,
            source="config",
        )
        for record in load_config_mcp_skills()
        if record.name not in db_names
    ]
    return ApiResponse(data=[*db_items, *config_items])


@router.post("/mcp-skills", response_model=ApiResponse[McpExternalSkillOut])
async def create_mcp_skill_for_ui(
    body: McpExternalSkillCreateIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[McpExternalSkillOut]:
    result = await mcp_skill_svc.create_mcp_skill(db, body)
    write_audit(
        db,
        user_id=user.id,
        action="mcp_external_skill.create",
        resource_type="mcp_external_skill",
        detail={"id": str(result.id), "name": result.name},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.patch("/mcp-skills/{skill_id}", response_model=ApiResponse[McpExternalSkillOut])
async def patch_mcp_skill_for_ui(
    skill_id: uuid.UUID,
    body: McpExternalSkillPatchIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[McpExternalSkillOut]:
    result = await mcp_skill_svc.patch_mcp_skill(db, skill_id, body)
    write_audit(
        db,
        user_id=user.id,
        action="mcp_external_skill.patch",
        resource_type="mcp_external_skill",
        detail={"id": str(skill_id), **body.model_dump(exclude_unset=True)},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/mcp-skills/{skill_id}/sync", response_model=ApiResponse[McpExternalSkillOut])
async def sync_mcp_skill_for_ui(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[McpExternalSkillOut]:
    result = await mcp_skill_svc.sync_mcp_skill_tools(db, skill_id)
    write_audit(
        db,
        user_id=user.id,
        action="mcp_external_skill.sync",
        resource_type="mcp_external_skill",
        detail={"id": str(skill_id), "tool_count": len(result.tools)},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.delete("/mcp-skills/{skill_id}", response_model=ApiResponse[dict])
def delete_mcp_skill_for_ui(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[dict]:
    mcp_skill_svc.delete_mcp_skill(db, skill_id)
    write_audit(
        db,
        user_id=user.id,
        action="mcp_external_skill.delete",
        resource_type="mcp_external_skill",
        detail={"id": str(skill_id)},
        ip_address=client_ip,
    )
    return ApiResponse(data={"deleted": True})


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


# ── 知识库文件夹挂载 ─────────────────────────────────────


@router.get(
    "/agents/{agent_id}/knowledge-mounts",
    response_model=ApiResponse[list[dict]],
)
def list_knowledge_mounts(
    agent_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[dict]]:
    from app.services.agent_knowledge_mount_service import list_mounts

    return ApiResponse(data=list_mounts(db, agent_id))


@router.post(
    "/agents/{agent_id}/knowledge-mounts",
    response_model=ApiResponse[dict],
)
def add_knowledge_mount(
    agent_id: str,
    body: KnowledgeMountCreateIn,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[dict]:
    from app.services.agent_knowledge_mount_service import add_mount

    result = add_mount(
        db, agent_id,
        dataset_id=body.dataset_id,
        folder_id=body.folder_id,
        scope=body.scope,
        label=body.label or None,
    )
    write_audit(
        db,
        user_id=user.id,
        action="agent_knowledge_mount.add",
        resource_type="agent_profile",
        detail={"agent_id": agent_id, "mount": result},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.delete(
    "/agents/{agent_id}/knowledge-mounts/{mount_id}",
    response_model=ApiResponse[None],
)
def remove_knowledge_mount(
    agent_id: str,
    mount_id: str,
    user: Annotated[User, Depends(require_permission("feature.agent_skills"))],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[None]:
    from app.services.agent_knowledge_mount_service import remove_mount

    remove_mount(db, agent_id, mount_id)
    write_audit(
        db,
        user_id=user.id,
        action="agent_knowledge_mount.remove",
        resource_type="agent_profile",
        detail={"agent_id": agent_id, "mount_id": mount_id},
        ip_address=client_ip,
    )
    return ApiResponse()
