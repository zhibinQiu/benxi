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
    resolve_kg_planning_context,
)
from app.core.agent_tool_context import (
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    trim_agent_loop_messages,
)
from app.services.agent_skill_router import is_skill_management_message
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
    agent_id: str | None = None,
    allowed_tool_names: set[str] | None = None,
    allowed_skill_names: set[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow 事件；结束时 yield type=complete。"""
    working: list[dict[str, Any]] = [dict(m) for m in messages]
    loop_id = f"agent-tools-{uuid.uuid4().hex[:8]}"
    plan_id = f"agent-plan-{uuid.uuid4().hex[:8]}"
    if tools is not None:
        all_tool_specs = tools
    elif allowed_tool_names is not None:
        all_tool_specs = build_agent_tool_specs(
            db, user, allowed_names=allowed_tool_names
        )
    else:
        all_tool_specs = build_agent_tool_specs(db, user)
    rounds = max_rounds if max_rounds is not None else _default_max_rounds()
    loop_state: dict[str, Any] = {
        "citations": [],
        "kg_context": None,
        "allowed_skill_names": allowed_skill_names,
    }

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "规划执行策略",
            "detail": "",
            "tool": "planner",
            "step_id": plan_id,
        },
    }

    kg_plan_text = resolve_kg_planning_context(db, user, user_message)
    if kg_plan_text:
        preview = kg_plan_text.replace("\n", " ")[:160]
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "本体图谱上下文",
                "detail": preview,
                "tool": "kg_context",
                "step_id": plan_id,
                "status": "done",
            },
        }

    execution_plan = await resolve_execution_plan(
        db,
        user,
        message=user_message,
        history=chat_history,
        intent_plan=intent_plan,
        available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
        kg_planning_context=kg_plan_text or None,
    )

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "规划完成",
            "detail": "",
            "tool": "planner",
            "step_id": plan_id,
            "status": "done",
        },
    }

    if execution_plan.direct_answer:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        reply_parts: list[str] = []
        async for ev in iter_llm_answer_events(
            messages=working,
            temperature=0.5,
            think_title="直接回答",
            think_detail=execution_plan.intent or "无需调用工具",
            step_id=loop_id,
        ):
            if ev.get("type") == "workflow":
                yield {"type": "workflow", "data": ev["data"]}
            elif ev.get("type") == "delta" and ev.get("text"):
                reply_parts.append(ev["text"])
                yield {"type": "delta", "text": ev["text"]}
        final_reply = "".join(reply_parts).strip() or None
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

    plan_has_script = None
    if execution_plan.uploaded_skill:
        from app.services.agent_skill_service import uploaded_skill_has_script

        try:
            plan_has_script = uploaded_skill_has_script(db, execution_plan.uploaded_skill)
        except Exception:
            plan_has_script = None
    plan_instruction = build_plan_context_instruction(
        execution_plan,
        uploaded_skill_has_script=plan_has_script,
    )
    working = _inject_plan_instruction(working, plan_instruction)
    initial_skill = (
        str(execution_plan.uploaded_skill or "").strip()
        or str(loop_state.get("planned_uploaded_skill") or "").strip()
    )
    allowed_skills = loop_state.get("allowed_skill_names")
    if (
        initial_skill
        and allowed_skills is not None
        and initial_skill not in allowed_skills
    ):
        initial_skill = ""
    if initial_skill:
        working = maybe_inject_skill_md(db, user, loop_state, working, initial_skill)

    final_reply: str | None = None

    for _ in range(max(1, rounds)):
        pending_skill = str(loop_state.get("pending_skill_md_inject") or "").strip()
        allowed_skills = loop_state.get("allowed_skill_names")
        if pending_skill and allowed_skills is not None and pending_skill not in allowed_skills:
            loop_state.pop("pending_skill_md_inject", None)
            pending_skill = ""
        if pending_skill:
            working = maybe_inject_skill_md(db, user, loop_state, working, pending_skill)
            loop_state.pop("pending_skill_md_inject", None)

        tool_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
        keep_tools = 2 if is_skill_management_message(user_message) else 1
        llm_messages = trim_agent_loop_messages(
            inject_retrieval_context_message(working, loop_state),
            keep_full_tool_results=keep_tools,
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
