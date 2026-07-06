"""外部 MCP Skill CRUD 与 tools 同步。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.core.mcp.client import mcp_list_tools
from app.core.mcp.external_registry import clear_mcp_skill_cache
from app.models.mcp_external_skill import McpExternalSkill
from app.schemas.mcp_external_skill import (
    McpExternalSkillCreateIn,
    McpExternalSkillOut,
    McpExternalSkillPatchIn,
    McpToolOut,
)
from app.skills.registry import ensure_skills_loaded, get_skill


def _tools_out(raw: list | None) -> list[McpToolOut]:
    if not isinstance(raw, list):
        return []
    out: list[McpToolOut] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        schema = item.get("inputSchema")
        if not isinstance(schema, dict):
            schema = {}
        out.append(
            McpToolOut(
                name=name,
                description=str(item.get("description") or ""),
                inputSchema=schema,
            )
        )
    return out


def _to_out(row: McpExternalSkill) -> McpExternalSkillOut:
    return McpExternalSkillOut(
        id=row.id,
        name=row.name,
        title=row.title or row.name,
        description=row.description or "",
        endpoint=row.endpoint,
        transport=row.transport or "http",
        enabled=bool(row.enabled),
        tools=_tools_out(row.tools_cache),
        use_when=row.use_when or "",
        dont_use_when=row.dont_use_when or "",
        output=row.output or "",
        source="db",
        created_at=row.created_at,
    )


async def _fetch_tools(
    endpoint: str,
    *,
    auth_token: str,
    transport: str,
) -> list[dict]:
    tools = await mcp_list_tools(
        endpoint,
        auth_token=auth_token,
        transport=transport,
    )
    return [dict(item) for item in tools if isinstance(item, dict)]


def list_mcp_skills_admin(db: Session) -> list[McpExternalSkillOut]:
    rows = db.scalars(
        select(McpExternalSkill).order_by(McpExternalSkill.created_at.desc())
    ).all()
    return [_to_out(row) for row in rows]


async def create_mcp_skill(db: Session, body: McpExternalSkillCreateIn) -> McpExternalSkillOut:
    ensure_skills_loaded()
    name = body.name.strip()
    if get_skill(name):
        raise bad_request(f"skill 名称 `{name}` 与内置 skill 冲突")
    existing_skill = db.scalar(select(McpExternalSkill).where(McpExternalSkill.name == name))
    if existing_skill is not None:
        raise bad_request(f"MCP skill `{name}` 已存在")
    from app.models.agent_skill import AgentSkill

    uploaded = db.scalar(select(AgentSkill).where(AgentSkill.name == name))
    if uploaded is not None:
        raise bad_request(f"skill 名称 `{name}` 与发展 skill 冲突")

    endpoint = body.endpoint.strip()
    transport = (body.transport or "http").strip().lower()
    tools_cache: list[dict] | None = None
    if body.sync_tools:
        tools_cache = await _fetch_tools(
            endpoint,
            auth_token=body.auth_token or "",
            transport=transport,
        )

    row = McpExternalSkill(
        id=uuid.uuid4(),
        name=name,
        title=(body.title or name).strip(),
        description=(body.description or "").strip(),
        endpoint=endpoint,
        transport=transport,
        auth_token=(body.auth_token or "").strip(),
        enabled=body.enabled,
        tools_cache=tools_cache,
        use_when=(body.use_when or "").strip(),
        dont_use_when=(body.dont_use_when or "").strip(),
        output=(body.output or "").strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    clear_mcp_skill_cache()
    return _to_out(row)


async def patch_mcp_skill(
    db: Session,
    skill_id: uuid.UUID,
    body: McpExternalSkillPatchIn,
) -> McpExternalSkillOut:
    row = db.get(McpExternalSkill, skill_id)
    if row is None:
        raise not_found("MCP skill 不存在")
    if body.title is not None:
        row.title = body.title.strip()
    if body.description is not None:
        row.description = body.description.strip()
    if body.endpoint is not None:
        endpoint = body.endpoint.strip()
        if not endpoint:
            raise bad_request("endpoint 不能为空")
        row.endpoint = endpoint
    if body.transport is not None:
        row.transport = body.transport.strip().lower()
    if body.auth_token is not None:
        row.auth_token = body.auth_token.strip()
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.use_when is not None:
        row.use_when = body.use_when.strip()
    if body.dont_use_when is not None:
        row.dont_use_when = body.dont_use_when.strip()
    if body.output is not None:
        row.output = body.output.strip()
    db.commit()
    db.refresh(row)
    clear_mcp_skill_cache()
    return _to_out(row)


async def sync_mcp_skill_tools(db: Session, skill_id: uuid.UUID) -> McpExternalSkillOut:
    row = db.get(McpExternalSkill, skill_id)
    if row is None:
        raise not_found("MCP skill 不存在")
    row.tools_cache = await _fetch_tools(
        row.endpoint,
        auth_token=row.auth_token or "",
        transport=(row.transport or "http").strip().lower(),
    )
    db.commit()
    db.refresh(row)
    clear_mcp_skill_cache()
    return _to_out(row)


def delete_mcp_skill(db: Session, skill_id: uuid.UUID) -> None:
    row = db.get(McpExternalSkill, skill_id)
    if row is None:
        raise not_found("MCP skill 不存在")
    db.delete(row)
    db.commit()
    clear_mcp_skill_cache()
