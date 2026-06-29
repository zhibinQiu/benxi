"""GB/Z 185.6 专精智能体 handoff 消息构建与解析。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.aip.aid import build_agent_aid, orchestrator_aid
from app.core.aip.types import AipDataItem, AipMessage, AipMessageType


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_message_id() -> str:
    return f"msg-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class SpecialistHandoffResult:
    ok: bool
    text: str
    message: AipMessage | None = None


def build_specialist_handoff_message(
    *,
    agent_id: str,
    session_id: str,
    task_id: str,
    text: str,
    loop_state: dict[str, Any] | None = None,
    satisfied: bool = True,
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> AipMessage:
    """服务智能体向请求智能体交还工作成果（work_artifact / task_response）。"""
    state = loop_state or {}
    data_items: list[AipDataItem] = [
        AipDataItem(
            dataType="text/plain",
            content=text,
            label="handoff_summary",
        )
    ]
    tool_outcomes = list(state.get("tool_outcome_lines") or [])
    if tool_outcomes:
        data_items.append(
            AipDataItem(
                dataType="application/json",
                content={"tool_outcomes": tool_outcomes[-8:]},
                label="tool_outcomes",
            )
        )
    skill_conclusion = str(state.get("last_skill_conclusion") or "").strip()
    if skill_conclusion:
        data_items.append(
            AipDataItem(
                dataType="application/json",
                content={"skill_conclusion": skill_conclusion},
                label="skill_conclusion",
            )
        )
    if citations:
        data_items.append(
            AipDataItem(
                dataType="application/json",
                content={"citations": citations[:20]},
                label="citations",
            )
        )
    if kg_context is not None:
        data_items.append(
            AipDataItem(
                dataType="application/json",
                content={"kg_context": kg_context},
                label="kg_context",
            )
        )

    msg_type = AipMessageType.TASK_RESPONSE if satisfied else AipMessageType.TASK_ERROR
    return AipMessage(
        id=_new_message_id(),
        senderRole="service",
        senderId=build_agent_aid(agent_id),
        targetId=orchestrator_aid(),
        sessionId=session_id,
        taskId=task_id,
        artifact=True,
        final=satisfied,
        lastChunk=True,
        message_type=msg_type,
        timestamp=_utc_now_iso(),
        dataItems=data_items,
        payload={
            "agent_id": agent_id,
            "satisfied": satisfied,
            "status": "done" if satisfied else "failed",
        },
    )


def build_specialist_handoff_result(
    *,
    ok: bool,
    text: str,
    agent_id: str,
    session_id: str,
    task_id: str,
    loop_state: dict[str, Any] | None = None,
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> SpecialistHandoffResult:
    if not ok or not (text or "").strip():
        return SpecialistHandoffResult(ok=False, text="", message=None)
    clean_agent = (agent_id or "").strip()
    if not clean_agent:
        return SpecialistHandoffResult(ok=True, text=text.strip(), message=None)
    message = build_specialist_handoff_message(
        agent_id=clean_agent,
        session_id=session_id or f"session-{uuid.uuid4().hex[:8]}",
        task_id=task_id or f"task-{uuid.uuid4().hex[:8]}",
        text=text.strip(),
        loop_state=loop_state,
        satisfied=True,
        citations=citations,
        kg_context=kg_context,
    )
    return SpecialistHandoffResult(ok=True, text=text.strip(), message=message)


def handoff_text_from_message(message: AipMessage | dict[str, Any] | None) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        try:
            message = AipMessage.model_validate(message)
        except Exception:
            return ""
    for item in message.dataItems:
        if item.label == "handoff_summary" and item.content:
            return str(item.content).strip()
    for item in message.dataItems:
        if item.dataType.startswith("text/") and item.content:
            return str(item.content).strip()
    return ""


def build_sequential_task_request(
    *,
    user_message: str,
    prior_handoffs: list[AipMessage],
    session_id: str,
    task_id: str,
    target_agent_id: str,
) -> AipMessage:
    """顺序编排：请求方向下一服务智能体下发 task_request，携带前置成果。"""
    prior_payload = [item.model_dump(mode="json") for item in prior_handoffs]
    data_items = [
        AipDataItem(
            dataType="text/plain",
            content=user_message.strip(),
            label="user_goal",
        ),
    ]
    if prior_handoffs:
        data_items.append(
            AipDataItem(
                dataType="application/json",
                content={"prior_handoffs": prior_payload},
                label="prior_handoffs",
            )
        )
    return AipMessage(
        id=_new_message_id(),
        senderRole="request",
        senderId=orchestrator_aid(),
        targetId=build_agent_aid(target_agent_id),
        sessionId=session_id,
        taskId=task_id,
        artifact=False,
        final=False,
        lastChunk=True,
        message_type=AipMessageType.TASK_REQUEST,
        timestamp=_utc_now_iso(),
        dataItems=data_items,
        payload={
            "action": "execute_task",
            "target_agent_id": target_agent_id,
            "prior_task_count": len(prior_handoffs),
        },
    )


def format_task_request_for_llm(request: AipMessage) -> str:
    """将 AIP task_request 转为专精 LLM 可读的 user 消息（向后兼容）。"""
    user_goal = ""
    prior_lines: list[str] = []
    for item in request.dataItems:
        if item.label == "user_goal" and item.content:
            user_goal = str(item.content).strip()
        if item.label == "prior_handoffs" and isinstance(item.content, dict):
            raw_list = item.content.get("prior_handoffs") or []
            for raw in raw_list:
                try:
                    msg = AipMessage.model_validate(raw)
                except Exception:
                    continue
                text = handoff_text_from_message(msg)
                if text:
                    agent_id = (msg.payload or {}).get("agent_id") or msg.senderId
                    prior_lines.append(f"- {agent_id}：{text[:240]}")
    parts = [user_goal] if user_goal else []
    if prior_lines:
        parts.append("【已完成】\n" + "\n".join(prior_lines))
    parts.append("请完成你负责的步骤并调用工具。")
    return "\n\n".join(part for part in parts if part.strip())
