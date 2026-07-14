"""GB/Z 185.6 专精智能体 handoff — agentkit 适配（保留平台 citations / kg 等扩展）。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.agent_loop_state import LoopState

from app.agentkit.aip.handoff import (
    SpecialistHandoffResult,
    build_sequential_task_request as _build_sequential_task_request,
    build_specialist_handoff_message as _build_specialist_handoff_message,
    format_task_request_for_llm,
    handoff_text_from_message,
)

from app.core.aip._platform_config import platform_handoff_builder
from app.agentkit.aip.types import AipDataItem, AipMessage

__all__ = [
    "SpecialistHandoffResult",
    "build_sequential_task_request",
    "build_specialist_assist_handoff",
    "build_specialist_handoff_message",
    "build_specialist_handoff_result",
    "format_task_request_for_llm",
    "handoff_text_from_message",
    "orchestrator_assist_from_complete",
]


def _extra_data_items(
    *,
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> list[AipDataItem]:
    items: list[AipDataItem] = []
    if citations:
        items.append(
            AipDataItem(
                dataType="application/json",
                content={"citations": citations[:20]},
                label="citations",
            )
        )
    if kg_context is not None:
        items.append(
            AipDataItem(
                dataType="application/json",
                content={"kg_context": kg_context},
                label="kg_context",
            )
        )
    return items


def build_specialist_handoff_message(
    *,
    agent_id: str,
    session_id: str,
    task_id: str,
    text: str,
    loop_state: LoopState | None = None,
    satisfied: bool = True,
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> AipMessage:
    extra = _extra_data_items(citations=citations, kg_context=kg_context)
    return _build_specialist_handoff_message(
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        text=text,
        loop_state=loop_state,
        satisfied=satisfied,
        builder=platform_handoff_builder(),
        extra_data_items=extra or None,
    )


def build_specialist_handoff_result(
    *,
    ok: bool,
    text: str,
    agent_id: str,
    session_id: str,
    task_id: str,
    loop_state: LoopState | None = None,
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


def build_specialist_assist_handoff(
    loop_state: LoopState | None,
    *,
    agent_id: str,
    session_id: str,
    task_id: str,
    assist: dict[str, Any],
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> SpecialistHandoffResult:
    """专精无法完成时向调度层反馈协助请求（TASK_ERROR + needs_assist）。"""
    clean_agent = (agent_id or "").strip()
    reason = str(assist.get("reason") or "").strip()
    needed = str(assist.get("needed_from") or "").strip()
    if not clean_agent or not reason:
        return SpecialistHandoffResult(ok=False, text="", message=None)
    text = f"需调度协助：{reason}"
    if needed:
        text = f"{text}（需要：{needed}）"
    message = build_specialist_handoff_message(
        agent_id=clean_agent,
        session_id=session_id or f"session-{uuid.uuid4().hex[:8]}",
        task_id=task_id or f"task-{uuid.uuid4().hex[:8]}",
        text=text,
        loop_state=loop_state,
        satisfied=False,
        citations=citations,
        kg_context=kg_context,
    )
    payload = dict(message.payload or {})
    payload.update(
        {
            "agent_id": clean_agent,
            "satisfied": False,
            "status": "needs_assist",
            "assist": assist,
        }
    )
    message = message.model_copy(update={"payload": payload})
    return SpecialistHandoffResult(ok=True, text=text, message=message)


def orchestrator_assist_from_complete(complete: dict[str, Any] | None) -> dict[str, Any] | None:
    """从 complete 事件解析专精向调度层发起的协助请求。"""
    from app.agentkit.aip.messaging import handoff_from_complete

    message = handoff_from_complete(complete)
    if message is None:
        return None
    payload = message.payload or {}
    if payload.get("status") != "needs_assist":
        return None
    assist = payload.get("assist")
    return assist if isinstance(assist, dict) else None


def build_sequential_task_request(
    *,
    user_message: str,
    prior_handoffs: list[AipMessage],
    session_id: str,
    task_id: str,
    target_agent_id: str,
) -> AipMessage:
    return _build_sequential_task_request(
        user_message=user_message,
        prior_handoffs=prior_handoffs,
        session_id=session_id,
        task_id=task_id,
        target_agent_id=target_agent_id,
        builder=platform_handoff_builder(),
    )
