"""外部 AIP 智能体 CRUD — 与配置项合并供发现与调用。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.models.aip_external_agent import AipExternalAgent
from app.schemas.aip_external_agent import (
    AipExternalAgentCreateIn,
    AipExternalAgentOut,
    AipExternalAgentPatchIn,
)


def _to_out(row: AipExternalAgent) -> AipExternalAgentOut:
    return AipExternalAgentOut(
        id=row.id,
        aid=row.aid,
        name=row.name,
        description=row.description or "",
        service_endpoint=row.service_endpoint,
        enabled=bool(row.enabled),
        source="db",
        created_at=row.created_at,
    )


def list_external_agents_admin(db: Session) -> list[AipExternalAgentOut]:
    rows = db.scalars(
        select(AipExternalAgent).order_by(AipExternalAgent.created_at.desc())
    ).all()
    return [_to_out(row) for row in rows]


def create_external_agent(
    db: Session,
    body: AipExternalAgentCreateIn,
) -> AipExternalAgentOut:
    aid = body.aid.strip()
    endpoint = body.service_endpoint.strip()
    if not aid or not endpoint:
        raise bad_request("AID 与 service_endpoint 不能为空")
    existing = db.scalar(select(AipExternalAgent).where(AipExternalAgent.aid == aid))
    if existing is not None:
        raise bad_request(f"AID 已存在: {aid}")
    row = AipExternalAgent(
        id=uuid.uuid4(),
        aid=aid,
        name=body.name.strip(),
        description=(body.description or "").strip(),
        service_endpoint=endpoint,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


def patch_external_agent(
    db: Session,
    agent_id: uuid.UUID,
    body: AipExternalAgentPatchIn,
) -> AipExternalAgentOut:
    row = db.get(AipExternalAgent, agent_id)
    if row is None:
        raise not_found("外部智能体不存在")
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description.strip()
    if body.service_endpoint is not None:
        endpoint = body.service_endpoint.strip()
        if not endpoint:
            raise bad_request("service_endpoint 不能为空")
        row.service_endpoint = endpoint
    if body.enabled is not None:
        row.enabled = body.enabled
    db.commit()
    db.refresh(row)
    return _to_out(row)


def delete_external_agent(db: Session, agent_id: uuid.UUID) -> None:
    row = db.get(AipExternalAgent, agent_id)
    if row is None:
        raise not_found("外部智能体不存在")
    db.delete(row)
    db.commit()
