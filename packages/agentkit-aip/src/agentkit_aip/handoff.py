"""GB/Z 185.6 专精智能体 handoff 消息构建与解析。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agentkit_aip.aid import AidConfig, build_agent_aid, orchestrator_aid
from agentkit_aip.types import AipDataItem, AipMessage, AipMessageType


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_message_id() -> str:
    return f"msg-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True, slots=True)
class HandoffBuilder:
    """Handoff 构建器：注入 AID 配置与可选的 loop_state 字段提取器。"""

    aid_config: AidConfig = field(default_factory=AidConfig)
    loop_state_extractors: tuple[Callable[[dict[str, Any]], AipDataItem | None], ...] = ()

    def agent_aid(self, agent_id: str) -> str:
        return build_agent_aid(agent_id, self.aid_config)

    def orchestrator(self) -> str:
        return orchestrator_aid(self.aid_config)


@dataclass(frozen=True, slots=True)
class HandoffParams:
    """构建 handoff 消息的通用参数（取代 8+ 参数函数）。"""

    agent_id: str
    session_id: str
    task_id: str
    text: str
    ok: bool = True
    loop_state: dict[str, Any] | None = None
    extra_data_items: list[AipDataItem] | None = None


@dataclass(frozen=True)
class SpecialistHandoffResult:
    ok: bool
    text: str
    message: AipMessage | None = None


def _default_loop_state_items(state: dict[str, Any]) -> list[AipDataItem]:
    items: list[AipDataItem] = []
    tool_outcomes = list(state.get("tool_outcome_lines") or [])
    if tool_outcomes:
        items.append(
            AipDataItem(
                dataType="application/json",
                content={"tool_outcomes": tool_outcomes[-8:]},
                label="tool_outcomes",
            )
        )
    skill_conclusion = str(state.get("last_skill_conclusion") or "").strip()
    if skill_conclusion:
        items.append(
            AipDataItem(
                dataType="application/json",
                content={"skill_conclusion": skill_conclusion},
                label="skill_conclusion",
            )
        )
    return items


def build_specialist_handoff_message(
    # 向后兼容 kwargs
    agent_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    text: str | None = None,
    *,
    loop_state: dict[str, Any] | None = None,
    satisfied: bool = True,
    builder: HandoffBuilder | None = None,
    extra_data_items: list[AipDataItem] | None = None,
    params: HandoffParams | None = None,
) -> AipMessage:
    """服务智能体向请求智能体交还工作成果。

    推荐使用 ``HandoffParams``::
        build_specialist_handoff_message(params=HandoffParams(...))

    也支持旧式 kwargs 调用（向后兼容）。
    """
    p = params or HandoffParams(
        agent_id=agent_id or "",
        session_id=session_id or "",
        task_id=task_id or "",
        text=text or "",
        ok=satisfied,
        loop_state=loop_state,
        extra_data_items=extra_data_items,
    )
    return _build_handoff(p, builder=builder)


def build_specialist_handoff_result(
    # 向后兼容 kwargs
    ok: bool = True,
    text: str = "",
    agent_id: str = "",
    session_id: str = "",
    task_id: str = "",
    *,
    loop_state: dict[str, Any] | None = None,
    builder: HandoffBuilder | None = None,
    extra_data_items: list[AipDataItem] | None = None,
    params: HandoffParams | None = None,
) -> SpecialistHandoffResult:
    """包装 handoff 构建，返回结果对象。

    推荐使用 ``HandoffParams``；也支持旧式 kwargs。
    """
    p = params or HandoffParams(
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        text=text,
        ok=ok,
        loop_state=loop_state,
        extra_data_items=extra_data_items,
    )
    if not p.ok or not (p.text or "").strip():
        return SpecialistHandoffResult(ok=False, text="", message=None)
    clean_agent = (p.agent_id or "").strip()
    if not clean_agent:
        return SpecialistHandoffResult(ok=True, text=p.text.strip(), message=None)
    msg_params = HandoffParams(
        agent_id=clean_agent,
        session_id=p.session_id or f"session-{uuid.uuid4().hex[:8]}",
        task_id=p.task_id or f"task-{uuid.uuid4().hex[:8]}",
        text=p.text.strip(),
        ok=True,
        loop_state=p.loop_state,
        extra_data_items=p.extra_data_items,
    )
    message = _build_handoff(msg_params, builder=builder)
    return SpecialistHandoffResult(ok=True, text=p.text.strip(), message=message)


def _build_handoff(
    params: HandoffParams,
    *,
    builder: HandoffBuilder | None = None,
) -> AipMessage:
    hb = builder or HandoffBuilder()
    state = params.loop_state or {}
    data_items: list[AipDataItem] = [
        AipDataItem(dataType="text/plain", content=params.text, label="handoff_summary"),
        *_default_loop_state_items(state),
    ]
    if params.extra_data_items:
        data_items.extend(params.extra_data_items)
    for extractor in hb.loop_state_extractors:
        item = extractor(state)
        if item is not None:
            data_items.append(item)

    msg_type = AipMessageType.TASK_RESPONSE if params.ok else AipMessageType.TASK_ERROR
    return AipMessage(
        id=_new_message_id(),
        senderRole="service",
        senderId=hb.agent_aid(params.agent_id),
        targetId=hb.orchestrator(),
        sessionId=params.session_id,
        taskId=params.task_id,
        artifact=True,
        final=params.ok,
        lastChunk=True,
        message_type=msg_type,
        timestamp=_utc_now_iso(),
        dataItems=data_items,
        payload={
            "agent_id": params.agent_id,
            "satisfied": params.ok,
            "status": "done" if params.ok else "failed",
        },
    )


# ── handoff 内容提取 ────────────────────────────────────────────


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


# ── 顺序编排 ─────────────────────────────────────────────────────


def build_sequential_task_request(
    *,
    user_message: str,
    prior_handoffs: list[AipMessage],
    session_id: str,
    task_id: str,
    target_agent_id: str,
    builder: HandoffBuilder | None = None,
) -> AipMessage:
    hb = builder or HandoffBuilder()
    prior_payload = [item.model_dump(mode="json") for item in prior_handoffs]
    data_items = [
        AipDataItem(dataType="text/plain", content=user_message.strip(), label="user_goal"),
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
        senderId=hb.orchestrator(),
        targetId=hb.agent_aid(target_agent_id),
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
