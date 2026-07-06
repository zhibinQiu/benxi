"""AIP（GB/Z 185）发现注册与同步调用服务。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.aip.acdl import build_agent_acdl, list_builtin_agent_acdl
from app.core.aip.aid import parse_agent_id_from_aid
from app.core.aip.external_registry import list_external_agents
from app.core.aip.types import AipInteractEnvelope
from app.core.exceptions import bad_request, not_found, service_unavailable
from app.models.org import User
from app.schemas.aip import AipAgentDetailOut, AipDiscoverItemOut, AipDiscoverOut
from app.services.agent_aip_executor import (
    execute_aip_interact,
    iter_execute_aip_interact_stream,
    resolve_target_agent_id,
)
from app.services.agent_profile_service import is_agent_enabled, is_agent_service_enabled


def _enabled_map(db: Session) -> dict[str, bool]:
    from app.core.agent_profiles import AGENT_PROFILES

    return {defn.id: is_agent_enabled(db, defn.id) for defn in AGENT_PROFILES}


def _service_enabled_map(db: Session) -> dict[str, bool]:
    from app.core.agent_profiles import AGENT_PROFILES

    return {defn.id: is_agent_service_enabled(db, defn.id) for defn in AGENT_PROFILES}


def discover_agents(
    db: Session,
    *,
    capability: str | None = None,
    q: str | None = None,
    include_orchestrator: bool = False,
) -> AipDiscoverOut:
    """发现内置 + 外部 AIP 智能体（GB/Z 185.5）。"""
    settings = get_settings()
    if not settings.aip_enabled:
        return AipDiscoverOut(total=0, items=[])

    items: list[AipDiscoverItemOut] = []
    cap_filter = (capability or "").strip().lower()
    keyword = (q or "").strip().lower()

    enabled_map = _enabled_map(db)
    service_map = _service_enabled_map(db)
    for acdl in list_builtin_agent_acdl(
        include_orchestrator=include_orchestrator,
        enabled_only=True,
        enabled_map=enabled_map,
        service_enabled_map=service_map,
    ):
        cap_ids = [cap.id for cap in acdl.capabilities]
        if cap_filter and cap_filter not in {c.lower() for c in cap_ids}:
            agent_id = parse_agent_id_from_aid(acdl.aid) or ""
            if cap_filter != f"cap:{agent_id}".lower():
                continue
        if keyword:
            hay = f"{acdl.name} {acdl.description} {' '.join(cap_ids)}".lower()
            if keyword not in hay:
                continue
        items.append(
            AipDiscoverItemOut(
                aid=acdl.aid,
                name=acdl.name,
                description=acdl.description,
                capability_ids=cap_ids,
                service_endpoint=acdl.service_endpoint,
            )
        )

    for record in list_external_agents(db, capability=capability, keyword=q):
        cap_ids = [cap.id for cap in record.capabilities]
        items.append(
            AipDiscoverItemOut(
                aid=record.aid,
                name=record.name,
                description=record.description,
                capability_ids=cap_ids,
                service_endpoint=record.service_endpoint,
            )
        )

    return AipDiscoverOut(total=len(items), items=items)


def get_agent_by_aid(db: Session, aid: str) -> AipAgentDetailOut:
    """按 AID 获取 ACDL 描述（内置或外部）。"""
    settings = get_settings()
    if not settings.aip_enabled:
        raise service_unavailable("AIP 未启用")

    from app.core.aip.external_registry import get_external_agent

    external = get_external_agent(aid, db)
    if external is not None:
        return AipAgentDetailOut(
            aid=external.aid,
            name=external.name,
            version="1.0.0",
            description=external.description,
            capabilities=list(external.capabilities),
            service_endpoint=external.service_endpoint,
            enabled=external.enabled,
        )

    agent_id = parse_agent_id_from_aid(aid)
    if not agent_id:
        raise bad_request(f"无效的 AID: {aid}")

    enabled = is_agent_service_enabled(db, agent_id)
    acdl = build_agent_acdl(agent_id, enabled=enabled)
    if not acdl:
        raise not_found(f"智能体不存在: {aid}")
    return AipAgentDetailOut(**acdl.model_dump(), enabled=enabled)


def _resolve_interact_target(envelope: AipInteractEnvelope) -> tuple[str, str, str, str]:
    """从 AIP 信封解析 builtin agent_id、user_message、session_id、task_id。"""
    target_aid = (envelope.target_aid or "").strip()
    user_message = ""
    task_id = ""

    if envelope.message is not None:
        msg = envelope.message
        if not target_aid and msg.targetId:
            target_aid = msg.targetId
        for item in msg.dataItems:
            if item.label in ("user_goal", "user_message") and item.content:
                user_message = user_message or str(item.content).strip()
        task_id = (msg.taskId or "").strip()

    if envelope.payload:
        user_message = user_message or str(
            envelope.payload.get("user_message") or envelope.payload.get("message") or ""
        ).strip()
        task_id = task_id or str(envelope.payload.get("task_id") or "").strip()

    agent_id = resolve_target_agent_id(aid=target_aid)
    if not agent_id and envelope.payload:
        agent_id = str(envelope.payload.get("target_agent_id") or "").strip()

    if not target_aid and not agent_id:
        raise bad_request("缺少 target_aid 或 target_agent_id")
    if not user_message:
        raise bad_request("缺少 user_message / user_goal")

    session_id = (
        (envelope.conversation_id or "").strip()
        or (envelope.message.sessionId if envelope.message else "")
        or f"aip-session-{uuid.uuid4().hex[:12]}"
    )
    task_id = task_id or f"aip-task-{uuid.uuid4().hex[:8]}"
    return agent_id, user_message, session_id, task_id


async def interact_with_agent(
    db: Session,
    user: User,
    envelope: AipInteractEnvelope,
):
    """对外 AIP 同步调用（委托统一执行层）。"""
    agent_id, user_message, session_id, task_id = _resolve_interact_target(envelope)
    return await execute_aip_interact(
        db,
        user,
        envelope,
        builtin_agent_id=agent_id,
        user_message=user_message,
        session_id=session_id,
        task_id=task_id,
    )


async def iter_interact_with_agent_stream(
    db: Session,
    user: User,
    envelope: AipInteractEnvelope,
):
    """流式 AIP 调用，产出 JSON 字符串供 SSE。"""
    import json

    agent_id, user_message, session_id, task_id = _resolve_interact_target(envelope)
    try:
        async for event in iter_execute_aip_interact_stream(
            db,
            user,
            envelope,
            builtin_agent_id=agent_id,
            user_message=user_message,
            session_id=session_id,
            task_id=task_id,
        ):
            if event.get("type") == "workflow":
                yield json.dumps({"workflow": event.get("data")}, ensure_ascii=False)
            elif event.get("type") == "attachment":
                yield json.dumps({"attachments": [event.get("data")]}, ensure_ascii=False)
            elif event.get("type") == "aip_interact":
                yield json.dumps({"aip_interact": event.get("data")}, ensure_ascii=False)
            else:
                yield json.dumps(event, ensure_ascii=False)
    except Exception as exc:
        from app.core.user_messages import sanitize_user_message

        message = sanitize_user_message(str(exc), fallback="AIP 调用失败")
        yield json.dumps({"error": message}, ensure_ascii=False)
