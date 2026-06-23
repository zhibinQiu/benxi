"""AI 智能体 tool-calling 多轮循环 — 规划后按需加载 Skill / 检索，并产出 workflow 事件。"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.deepseek_client import chat_completion_message_async
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import AgentToolPlan
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    build_plan_context_instruction,
    filter_tool_specs_by_plan,
    resolve_execution_plan,
)
from app.core.agent_tool_context import (
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    trim_agent_loop_messages,
)
from app.services.agent_tools import (
    build_agent_tool_specs,
    execute_agent_tool,
    maybe_inject_skill_md,
    tool_workflow_meta,
)

_logger = logging.getLogger(__name__)


def _default_max_rounds() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "agent_max_tool_rounds", 40) or 40))


def _parse_tool_summary(result_text: str) -> tuple[bool, str]:
    try:
        body = json.loads(result_text)
        if isinstance(body, dict):
            return bool(body.get("ok")), str(body.get("summary") or "")
    except json.JSONDecodeError:
        pass
    return False, result_text[:200]


def _workflow_result_title(meta: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return str(meta.get("result_title") or meta.get("title") or "完成")
    failure = meta.get("failure_title")
    if failure:
        return str(failure)
    base = str(meta.get("title") or meta.get("result_title") or "操作")
    return f"{base}（失败）"


def _inject_plan_instruction(
    messages: list[dict[str, Any]],
    instruction: str,
) -> list[dict[str, Any]]:
    if not instruction.strip():
        return messages
    out = [dict(m) for m in messages]
    out.append({"role": "system", "content": instruction})
    return out


def _available_atomic_from_specs(specs: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for spec in specs:
        name = str((spec.get("function") or {}).get("name") or "")
        if name in RETRIEVAL_ATOMIC_TOOLS:
            names.add(name)
    return names


async def iter_agent_tool_loop(
    db: Session,
    user: User,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None = None,
    max_rounds: int | None = None,
    user_message: str = "",
    attachment_session_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow 事件；结束时 yield type=complete。"""
    working: list[dict[str, Any]] = [dict(m) for m in messages]
    loop_id = f"agent-tools-{uuid.uuid4().hex[:8]}"
    plan_id = f"agent-plan-{uuid.uuid4().hex[:8]}"
    all_tool_specs = tools if tools is not None else build_agent_tool_specs(db, user)
    rounds = max_rounds if max_rounds is not None else _default_max_rounds()
    loop_state: dict[str, Any] = {"citations": [], "kg_context": None}

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "规划执行策略",
            "detail": (user_message or "").strip()[:160],
            "tool": "planner",
            "step_id": plan_id,
        },
    }

    execution_plan = await resolve_execution_plan(
        db,
        user,
        message=user_message,
        history=chat_history,
        intent_plan=intent_plan,
        available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
    )

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "规划完成",
            "detail": execution_plan.summary_for_ui(),
            "tool": "planner",
            "step_id": plan_id,
            "status": "done",
        },
    }

    if execution_plan.direct_answer:
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thinking",
                "title": "直接回答",
                "detail": execution_plan.intent or "无需调用工具",
                "tool": "agent.direct",
                "step_id": loop_id,
            },
        }
        choice = await chat_completion_message_async(
            messages=working,
            tools=None,
            temperature=0.5,
        )
        final_reply = (
            (((choice or {}).get("message") or {}).get("content") or "").strip()
            or None
        )
        if final_reply:
            working.append({"role": "assistant", "content": final_reply})
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "回答完成",
                    "detail": "已直接生成回复",
                    "tool": "agent.direct",
                    "step_id": loop_id,
                    "status": "done",
                },
            }
        yield {
            "type": "complete",
            "messages": working,
            "reply": final_reply,
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        return

    plan_instruction = build_plan_context_instruction(execution_plan)
    working = _inject_plan_instruction(working, plan_instruction)
    initial_skill = (
        str(execution_plan.uploaded_skill or "").strip()
        or str(loop_state.get("planned_uploaded_skill") or "").strip()
    )
    if initial_skill:
        working = maybe_inject_skill_md(db, user, loop_state, working, initial_skill)

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "智能体工具调度",
            "detail": f"按计划调用工具（最多 {rounds} 轮）",
            "tool": "agent.tools",
            "step_id": loop_id,
        },
    }

    final_reply: str | None = None

    for _ in range(max(1, rounds)):
        pending_skill = str(loop_state.get("pending_skill_md_inject") or "").strip()
        if pending_skill:
            working = maybe_inject_skill_md(db, user, loop_state, working, pending_skill)
            loop_state.pop("pending_skill_md_inject", None)

        tool_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
        llm_messages = trim_agent_loop_messages(
            inject_retrieval_context_message(working, loop_state)
        )
        choice = await chat_completion_message_async(
            messages=llm_messages,
            tools=tool_specs or None,
            temperature=0.3,
        )
        if not choice:
            break
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()

        if tool_calls:
            working.append(message)
            for tc in tool_calls:
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                tool_name = str(fn.get("name") or "")
                tool_id = str(tc.get("id") or uuid.uuid4())
                raw_args = fn.get("arguments") or "{}"
                step_id = f"agent-tool-{uuid.uuid4().hex[:8]}"
                meta = tool_workflow_meta(tool_name, raw_args)
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "tool_call",
                        "title": meta["title"],
                        "detail": meta.get("detail") or "",
                        "tool": meta.get("tool") or tool_name,
                        "tool_name": tool_name,
                        "step_id": step_id,
                    },
                }
                result_text = await execute_agent_tool(
                    db,
                    user,
                    tool_name=tool_name,
                    arguments=raw_args,
                    conversation_id=conversation_id,
                    attachment_session_id=attachment_session_id,
                    user_message=user_message,
                    loop_state=loop_state,
                )
                ok, summary = _parse_tool_summary(result_text)
                result_data = {
                    "phase": "tool_result",
                    "title": _workflow_result_title(meta, ok=ok),
                    "detail": summary or ("完成" if ok else "失败"),
                    "tool": meta.get("tool") or tool_name,
                    "tool_name": tool_name,
                    "step_id": step_id,
                    "status": "done" if ok else "failed",
                }
                boost_seconds = meta.get("boost_seconds")
                if boost_seconds is not None:
                    result_data["boost_seconds"] = int(boost_seconds)
                yield {
                    "type": "workflow",
                    "data": result_data,
                }
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": compress_tool_result_for_loop(result_text),
                    }
                )
                for att in list(loop_state.get("stream_attachments") or []):
                    yield {"type": "attachment", "data": att}
                loop_state["stream_attachments"] = []
            continue

        if content:
            final_reply = content
            working.append({"role": "assistant", "content": content})
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "工具调度完成",
                    "detail": "已生成回答",
                    "tool": "agent.tools",
                    "step_id": loop_id,
                    "status": "done",
                },
            }
            break

        if message:
            working.append(message)
        break

    yield {
        "type": "complete",
        "messages": working,
        "reply": final_reply,
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }
