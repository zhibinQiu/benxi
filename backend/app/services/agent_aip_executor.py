"""AIP 智能体统一执行层 — 内置专精 hop 与外部 AIP 服务调用。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_loop_session import AgentLoopSession, coerce_user_id
from app.core.agent_profiles import get_agent_profile, resolve_agent_title
from app.core.aip.aid import build_agent_aid, orchestrator_aid, parse_agent_id_from_aid
from app.core.aip.external_registry import get_external_agent, is_external_aid
from app.core.aip.handoff import build_specialist_handoff_message
from app.agentkit.aip.messaging import handoff_from_complete, reply_text_from_complete
from app.core.aip.session_bus import get_session_bus
from app.agentkit.aip.types import AipInteractEnvelope, AipMessage, AipMessageType
from app.core.exceptions import bad_request, not_found, service_unavailable
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.schemas.aip import AipInteractOut
from app.services.agent_intent import AgentToolPlan
from app.services.agent_profile_service import (
    is_agent_enabled,
    is_agent_service_enabled,
    resolve_agent_skill_names,
)
from app.services.agent_specialist_context import build_specialist_chat_messages

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpecialistExecutionContext:
    """单次专精智能体执行上下文（内置 / 编排 / 对外 AIP 共用）。"""

    agent_id: str
    user_message: str
    session_id: str
    task_id: str
    reason: str = ""
    chat_history: list[AiChatMessage] | None = None
    retrieval_context: str = ""
    context_instruction: str = ""
    attachment_session_id: str | None = None
    intent_plan: AgentToolPlan | None = None
    max_rounds: int | None = None
    task_mode: bool = True


def is_builtin_agent(agent_id: str) -> bool:
    """是否为平台内置智能体（非外部 AIP 登记）。"""
    return get_agent_profile((agent_id or "").strip()) is not None


def resolve_target_agent_id(*, aid: str = "", agent_id: str = "") -> str:
    """从 AID 或 agent_id 解析内置 agent_id；外部 AID 返回空字符串。"""
    clean_aid = (aid or "").strip()
    if clean_aid and is_external_aid(clean_aid):
        return ""
    parsed = parse_agent_id_from_aid(clean_aid) if clean_aid else ""
    if parsed:
        return parsed
    return (agent_id or "").strip()


def _annotate_workflow(
    event: dict[str, Any],
    *,
    agent_id: str,
    agent_title: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    if event.get("type") != "workflow":
        return event
    data = dict(event.get("data") or {})
    data["agent_id"] = agent_id
    data["agent_title"] = agent_title
    if task_id:
        data["task_id"] = task_id
    return {"type": "workflow", "data": data}


async def iter_builtin_specialist_hop(
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    ctx: SpecialistExecutionContext,
) -> AsyncIterator[dict[str, Any]]:
    """执行内置专精智能体 hop，产出 workflow / complete 事件流。"""
    agent_id = ctx.agent_id
    agent_title = resolve_agent_title(agent_id)

    route_step_id = f"agent-route-{uuid.uuid4().hex[:8]}"
    route_data: dict[str, Any] = {
        "phase": "agent_thought",
        "title": agent_title,
        "detail": ctx.reason,
        "tool": "supervisor.route",
        "step_id": route_step_id,
        "status": "done",
        "agent_id": agent_id,
        "agent_title": agent_title,
    }
    if ctx.task_id:
        route_data["task_id"] = ctx.task_id
    yield {"type": "workflow", "data": route_data}

    db, user = sess.open()
    try:
        working_messages = build_specialist_chat_messages(
            db,
            user,
            agent_id=agent_id,
            message=ctx.user_message,
            history=ctx.chat_history,
            retrieval_context=ctx.retrieval_context,
            context_instruction=ctx.context_instruction,
            task_mode=ctx.task_mode,
            # 将路由原因作为额外指令注入，让 agent 知道自己被选中执行什么任务
            route_reason=ctx.reason,
        )
        skill_names = resolve_agent_skill_names(db, agent_id)
        # orchestrator 是通用智能体，不限制可用 skill
        allowed_skills = None if agent_id == "orchestrator" else set(skill_names)
    finally:
        sess.release_before_io()

    settings = get_settings()
    if agent_id == "orchestrator":
        specialist_rounds = min(8, ctx.max_rounds or 8)
        hop_task_mode = False
    else:
        specialist_rounds = min(
            settings.agent_specialist_max_tool_rounds,
            ctx.max_rounds or settings.agent_specialist_max_tool_rounds,
        )
        hop_task_mode = ctx.task_mode

    from app.services.agent_tool_loop import iter_agent_tool_loop

    async for event in iter_agent_tool_loop(
        user_id,
        working_messages,
        conversation_id=ctx.session_id,
        max_rounds=specialist_rounds,
        user_message=ctx.user_message,
        attachment_session_id=ctx.attachment_session_id,
        intent_plan=ctx.intent_plan,
        chat_history=ctx.chat_history,
        agent_id=agent_id,
        allowed_tool_names=None,
        allowed_skill_names=allowed_skills,
        task_mode=hop_task_mode,
        task_id=ctx.task_id,
    ):
        yield _annotate_workflow(
            event,
            agent_id=agent_id,
            agent_title=agent_title,
            task_id=ctx.task_id,
        )


def record_handoff_to_session(session_id: str, complete: dict[str, Any] | None) -> AipMessage | None:
    """从 complete 提取 handoff 并发布到会话总线，供后续子智能体读取。"""
    message = handoff_from_complete(complete)
    if message is not None:
        get_session_bus().publish(session_id, message)
    return message


async def invoke_external_agent(
    envelope: AipInteractEnvelope,
    *,
    db: Session | None = None,
    timeout_sec: float = 120.0,
) -> AipMessage:
    """调用外部 AIP 服务智能体（HTTP POST 至 service_endpoint）。"""
    target_aid = (envelope.target_aid or "").strip()
    if envelope.message and envelope.message.targetId:
        target_aid = target_aid or envelope.message.targetId.strip()
    record = get_external_agent(target_aid, db)
    if record is None:
        raise not_found(f"外部智能体未登记: {target_aid}")

    headers: dict[str, str] = {}
    token = (envelope.auth_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = envelope.model_dump(mode="json")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            response = await client.post(
                record.service_endpoint, json=payload, headers=headers
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        _logger.exception("外部 AIP 调用失败 aid=%s", target_aid)
        raise service_unavailable(f"外部智能体调用失败: {exc}") from exc

    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict) and "message" in data:
        try:
            return AipInteractOut.model_validate(data).message
        except Exception:
            pass
    if isinstance(data, dict) and "id" in data and "senderRole" in data:
        return AipMessage.model_validate(data)
    if isinstance(body, dict) and "message" in body:
        return AipMessage.model_validate(body["message"])
    raise bad_request("外部智能体返回格式不符合 AIP 约定")


def build_interact_result(
    *,
    agent_id: str,
    session_id: str,
    task_id: str,
    complete: dict[str, Any] | None,
    external_message: AipMessage | None = None,
) -> AipInteractOut:
    """将 hop complete 或外部响应统一封装为 AipInteractOut。"""
    message = external_message or handoff_from_complete(complete)
    reply_text = reply_text_from_complete(complete) if external_message is None else ""
    if external_message is not None:
        from app.core.aip.handoff import handoff_text_from_message

        reply_text = handoff_text_from_message(external_message)
    satisfied = bool(reply_text)

    if message is None:
        message = build_specialist_handoff_message(
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            text=reply_text or "未能完成请求",
            satisfied=satisfied,
        )
        if not satisfied:
            message.message_type = AipMessageType.TASK_ERROR
            message.final = False

    if message is not None and satisfied:
        get_session_bus().publish(session_id, message)

    return AipInteractOut(
        message=message,
        reply_text=reply_text,
        satisfied=satisfied,
        meta={
            "source_aid": orchestrator_aid(),
            "target_aid": build_agent_aid(agent_id) if is_builtin_agent(agent_id) else "",
            "session_id": session_id,
            "task_id": task_id,
        },
    )


async def execute_aip_interact(
    db: Session,
    user: User,
    envelope: AipInteractEnvelope,
    *,
    builtin_agent_id: str,
    user_message: str,
    session_id: str,
    task_id: str,
) -> AipInteractOut:
    """统一 AIP 调用入口：内置本地执行或转发外部 endpoint。"""
    settings = get_settings()
    if not settings.aip_enabled:
        raise service_unavailable("AIP 未启用")

    target_aid = (envelope.target_aid or "").strip()
    if target_aid and is_external_aid(target_aid, db):
        external_message = await invoke_external_agent(envelope, db=db)
        return build_interact_result(
            agent_id=parse_agent_id_from_aid(target_aid) or target_aid,
            session_id=session_id,
            task_id=task_id,
            complete=None,
            external_message=external_message,
        )

    if not builtin_agent_id or not is_builtin_agent(builtin_agent_id):
        raise not_found(f"智能体不存在: {builtin_agent_id or target_aid}")
    if not is_agent_enabled(db, builtin_agent_id):
        raise not_found(f"智能体未启用: {builtin_agent_id}")
    if not is_agent_service_enabled(db, builtin_agent_id):
        raise not_found(f"智能体服务未开放: {builtin_agent_id}")

    user_id = coerce_user_id(user.id)
    sess = AgentLoopSession(user_id)
    ctx = SpecialistExecutionContext(
        agent_id=builtin_agent_id,
        user_message=user_message,
        session_id=session_id,
        task_id=task_id,
        reason="AIP task_request",
        task_mode=True,
        max_rounds=settings.agent_specialist_max_tool_rounds,
    )
    complete: dict[str, Any] | None = None
    try:
        async for event in iter_builtin_specialist_hop(sess, user_id, ctx):
            if event.get("type") == "complete":
                complete = event
    finally:
        sess.close()

    return build_interact_result(
        agent_id=builtin_agent_id,
        session_id=session_id,
        task_id=task_id,
        complete=complete,
    )


async def iter_execute_aip_interact_stream(
    db: Session,
    user: User,
    envelope: AipInteractEnvelope,
    *,
    builtin_agent_id: str,
    user_message: str,
    session_id: str,
    task_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """流式 AIP 调用：产出 workflow / attachment 事件，最终以 aip_interact 结束。"""
    settings = get_settings()
    if not settings.aip_enabled:
        raise service_unavailable("AIP 未启用")

    target_aid = (envelope.target_aid or "").strip()
    if target_aid and is_external_aid(target_aid, db):
        external_message = await invoke_external_agent(envelope, db=db)
        result = build_interact_result(
            agent_id=parse_agent_id_from_aid(target_aid) or target_aid,
            session_id=session_id,
            task_id=task_id,
            complete=None,
            external_message=external_message,
        )
        yield {"type": "aip_interact", "data": result.model_dump(mode="json")}
        return

    if not builtin_agent_id or not is_builtin_agent(builtin_agent_id):
        raise not_found(f"智能体不存在: {builtin_agent_id or target_aid}")
    if not is_agent_enabled(db, builtin_agent_id):
        raise not_found(f"智能体未启用: {builtin_agent_id}")
    if not is_agent_service_enabled(db, builtin_agent_id):
        raise not_found(f"智能体服务未开放: {builtin_agent_id}")

    user_id = coerce_user_id(user.id)
    sess = AgentLoopSession(user_id)
    ctx = SpecialistExecutionContext(
        agent_id=builtin_agent_id,
        user_message=user_message,
        session_id=session_id,
        task_id=task_id,
        reason="AIP task_request",
        task_mode=True,
        max_rounds=settings.agent_specialist_max_tool_rounds,
    )
    complete: dict[str, Any] | None = None
    try:
        async for event in iter_builtin_specialist_hop(sess, user_id, ctx):
            if event.get("type") == "complete":
                complete = event
                continue
            yield event
    finally:
        sess.close()

    result = build_interact_result(
        agent_id=builtin_agent_id,
        session_id=session_id,
        task_id=task_id,
        complete=complete,
    )
    yield {"type": "aip_interact", "data": result.model_dump(mode="json")}
