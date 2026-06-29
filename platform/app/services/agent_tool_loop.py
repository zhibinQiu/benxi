"""AI 智能体 tool-calling 多轮循环 — 规划后按需加载 Skill / 检索，并产出 workflow 事件。"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_loop_session import AgentLoopSession
from app.core.aip.messaging import attach_handoff_to_complete
from app.integrations.deepseek_client import chat_completion_message_async
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    AgentExecutionPlan,
    build_plan_context_instruction,
    filter_tool_specs_by_plan,
    resolve_execution_plan,
    resolve_kg_planning_context,
)
from app.core.agent_message_parse import (
    assistant_content_is_deliverable,
    content_has_dsml_markup,
    normalize_llm_assistant_message,
    strip_dsml_markup,
)
from app.core.agent_tool_context import (
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    trim_agent_loop_messages,
)
from app.services.agent_reply_synth import (
    build_specialist_handoff,
    synthesize_tool_loop_user_reply,
)
from app.services.agent_skill_router import is_skill_management_message
from app.core.report_skill_catalog import REPORT_SKILL_NAME_SET
from app.services.report_agent_skills import (
    pick_available_report_skill,
    report_skill_label,
)
from app.services.agent_tools import (
    build_agent_tool_specs,
    execute_agent_tool,
    maybe_inject_skill_md,
    record_stream_screenshot_attachment,
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


def _finalize_loop_reply(reply: str | None, loop_state: dict[str, Any]) -> str | None:
    from app.services.agent_orchestrator import append_screenshot_markdown_to_reply

    attachments = list(loop_state.get("collected_attachments") or [])
    if not attachments:
        return reply
    return append_screenshot_markdown_to_reply(reply, attachments)


def _streamed_attachment_urls(loop_state: dict[str, Any]) -> set[str]:
    return {
        str(url).strip()
        for url in (loop_state.get("streamed_attachment_urls") or [])
        if str(url).strip()
    }


def _mark_streamed_attachment(loop_state: dict[str, Any], att: dict[str, Any]) -> None:
    url = str(att.get("url") or "").strip()
    if not url:
        return
    seen = _streamed_attachment_urls(loop_state)
    seen.add(url)
    loop_state["streamed_attachment_urls"] = sorted(seen)


def _pending_screenshot_attachments(loop_state: dict[str, Any]) -> list[dict[str, Any]]:
    """尚未通过 SSE attachment 下发的截图。"""
    streamed = _streamed_attachment_urls(loop_state)
    pending: list[dict[str, Any]] = []
    for att in list(loop_state.get("collected_attachments") or []):
        if not isinstance(att, dict):
            continue
        url = str(att.get("url") or "").strip()
        if not url or url in streamed:
            continue
        pending.append(dict(att))
        streamed.add(url)
    loop_state["streamed_attachment_urls"] = sorted(streamed)
    return pending


async def _maybe_auto_browser_screenshot(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    loop_state: dict[str, Any],
    user_message: str,
) -> None:
    """用户要求截图且已操作浏览器但未截图时，补拍一张。"""
    from app.services.agent_skill_router import user_wants_browser_screenshot

    if not user_wants_browser_screenshot(user_message):
        return
    if not loop_state.get("browser_session_used"):
        return
    if loop_state.get("collected_attachments"):
        return
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config
    from app.services import browser_rpa_service as rpa

    if not get_browser_rpa_config(db).enabled:
        return
    try:
        data = await rpa.browser_screenshot(db, user, conversation_id=conversation_id)
        record_stream_screenshot_attachment(loop_state, data)
    except Exception as exc:
        _logger.warning("自动浏览器截图失败: %s", exc)


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


def _narrow_execution_plan_for_specialist(
    plan: AgentExecutionPlan,
    *,
    agent_id: str | None,
    allowed_skill_names: set[str] | None,
    user_message: str = "",
) -> AgentExecutionPlan:
    """专精智能体：限制 uploaded_skill；生图/报告域默认挂载对应 Skill。"""
    if allowed_skill_names is not None and plan.uploaded_skill:
        if plan.uploaded_skill not in allowed_skill_names:
            plan = replace(plan, uploaded_skill=None)

    aid = (agent_id or "").strip()
    if aid == "diagram" and allowed_skill_names and "mermaid-diagram" in allowed_skill_names:
        if plan.uploaded_skill != "mermaid-diagram":
            return replace(
                plan,
                intent=plan.intent or "生成 Mermaid 图表",
                direct_answer=False,
                atomic_tools=(),
                skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
                uploaded_skill="mermaid-diagram",
                builtin_orchestration=None,
                steps=("按 mermaid-diagram 技能生成图表",),
            )
    if aid == "report" and allowed_skill_names:
        available_report = allowed_skill_names & REPORT_SKILL_NAME_SET
        skill = plan.uploaded_skill
        if skill not in available_report:
            skill = pick_available_report_skill(user_message, available_report)
        if skill and skill in available_report:
            atomic = tuple(plan.atomic_tools) or (
                ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
                ATOMIC_TOOL_WEB_SEARCH,
            )
            return replace(
                plan,
                intent=plan.intent or "撰写结构化报告",
                direct_answer=False,
                atomic_tools=atomic,
                skip_tools=(),
                uploaded_skill=skill,
                builtin_orchestration=None,
                steps=plan.steps
                or (
                    f"load_uploaded_skill({skill})",
                    "检索材料",
                    "按 Skill 模板输出长报告",
                ),
            )
    return plan


def _build_report_page_execution_plan(
    *,
    message: str,
    forced_skill: str | None,
    allowed_skill_names: set[str] | None,
) -> AgentExecutionPlan | None:
    """报告功能页：仅按报告类型 Skill 收集材料并撰写，不走通用意图规划。"""
    available = (allowed_skill_names or set()) & REPORT_SKILL_NAME_SET
    if not available:
        return None
    skill = (forced_skill or "").strip()
    if skill not in available:
        skill = pick_available_report_skill(message, available) or ""
    if not skill:
        return None
    label = report_skill_label(skill)
    return AgentExecutionPlan(
        reasoning=f"报告功能页：按 {skill} 模板收集材料并撰写{label}",
        intent=f"撰写{label}",
        direct_answer=False,
        atomic_tools=(
            ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            ATOMIC_TOOL_WEB_SEARCH,
        ),
        skip_tools=(),
        uploaded_skill=skill,
        builtin_orchestration=None,
        steps=(
            f"load_uploaded_skill({skill}) 读取报告模板",
            "knowledge_retrieve / web_search 收集材料",
            "按 templates/outline.md 输出 Markdown 长报告",
        ),
        source="rule",
    )


def _emit_report_reply_deltas(text: str, *, chunk_size: int = 600) -> list[dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return []
    return [
        {"type": "delta", "text": body[i : i + chunk_size]}
        for i in range(0, len(body), chunk_size)
    ]


async def iter_agent_tool_loop(
    user: User | uuid.UUID,
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
    report_write_mode: bool = False,
    scoped_doc_ids: list[str] | None = None,
    local_kb_disabled: bool = False,
    report_intent: str = "initial",
    forced_report_skill: str | None = None,
    report_topic: str = "",
    task_mode: bool = False,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow 事件；结束时 yield type=complete。内部按轮次管理 DB 会话。"""
    from app.core.agent_loop_session import coerce_user_id

    user_id = coerce_user_id(user)
    sess = AgentLoopSession(user_id)
    try:
        db, user = sess.open()
        async for event in _iter_agent_tool_loop_body(
            sess,
            db,
            user,
            messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            agent_id=agent_id,
            allowed_tool_names=allowed_tool_names,
            allowed_skill_names=allowed_skill_names,
            report_write_mode=report_write_mode,
            scoped_doc_ids=scoped_doc_ids,
            local_kb_disabled=local_kb_disabled,
            report_intent=report_intent,
            forced_report_skill=forced_report_skill,
            report_topic=report_topic,
            task_mode=task_mode,
            task_id=task_id,
        ):
            yield event
    finally:
        sess.close()


async def _iter_agent_tool_loop_body(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    agent_id: str | None,
    allowed_tool_names: set[str] | None,
    allowed_skill_names: set[str] | None,
    report_write_mode: bool,
    scoped_doc_ids: list[str] | None,
    local_kb_disabled: bool,
    report_intent: str,
    forced_report_skill: str | None,
    report_topic: str,
    task_mode: bool,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    uid = user.id
    working: list[dict[str, Any]] = [dict(m) for m in messages]
    loop_id = f"agent-tools-{uuid.uuid4().hex[:8]}"
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
        "_all_tool_specs": all_tool_specs,
        "report_write_mode": report_write_mode,
        "scoped_doc_ids": list(scoped_doc_ids) if scoped_doc_ids is not None else None,
        "local_kb_disabled": local_kb_disabled,
        "report_intent": report_intent,
        "forced_report_skill": forced_report_skill,
        "report_topic": (report_topic or "").strip(),
        "task_mode": task_mode,
    }

    if not report_write_mode:
        from app.services.kg_service import try_department_members_deterministic_reply

        dept_reply = try_department_members_deterministic_reply(db, user, user_message)
        if dept_reply:
            loop_state["deterministic_reply"] = dept_reply
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "已从本体图谱读取部门成员",
                    "detail": "",
                    "tool": "kg.org_members",
                    "step_id": loop_id,
                    "status": "done",
                },
            }
            yield {
                "type": "complete",
                "messages": working,
                "reply": dept_reply,
                "citations": [],
                "kg_context": loop_state.get("kg_context"),
            }
            return

    kg_plan_text = ""
    if not report_write_mode:
        from app.services.agent_intent import is_chitchat_message
        from app.services.agent_routing_signals import is_trivial_direct_question

        skip_kg_plan = is_chitchat_message(user_message, chat_history) or is_trivial_direct_question(
            user_message
        )
        if not skip_kg_plan:
            kg_plan_text = resolve_kg_planning_context(
                db, user, user_message, history=chat_history
            )

    if report_write_mode:
        execution_plan = _build_report_page_execution_plan(
            message=user_message,
            forced_skill=forced_report_skill,
            allowed_skill_names=allowed_skill_names,
        )
        if execution_plan is None:
            execution_plan = AgentExecutionPlan(
                reasoning="报告撰写",
                intent="撰写报告",
                direct_answer=False,
                atomic_tools=(
                    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
                    ATOMIC_TOOL_WEB_SEARCH,
                ),
                skip_tools=(),
                uploaded_skill=None,
                builtin_orchestration=None,
                steps=(),
                source="rule",
            )
    else:
        plan_step_id = f"agent-plan-{uuid.uuid4().hex[:8]}"
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thinking",
                "title": "正在规划执行步骤",
                "detail": "",
                "tool": "planner",
                "step_id": plan_step_id,
            },
        }
        sess.release_before_io()
        db, user = sess.open()
        execution_plan = await resolve_execution_plan(
            db,
            user,
            message=user_message,
            history=chat_history,
            intent_plan=intent_plan,
            available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
            kg_planning_context=kg_plan_text or None,
        )
        sess.release_before_io()
        db, user = sess.open()
        plan_summary = execution_plan.summary_for_ui()
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": f"规划方案：{execution_plan.intent or '执行步骤'}",
                "detail": plan_summary,
                "tool": "planner",
                "step_id": plan_step_id,
                "status": "done",
            },
        }

    execution_plan = _narrow_execution_plan_for_specialist(
        execution_plan,
        agent_id=agent_id,
        allowed_skill_names=allowed_skill_names,
        user_message=user_message,
    )

    if (
        allowed_tool_names is not None
        and not allowed_tool_names
        and not execution_plan.direct_answer
        and (
            execution_plan.atomic_tools
            or any(
                token in " ".join(execution_plan.steps).lower()
                for token in ("web_search", "knowledge_retrieve", "kg_query")
            )
        )
    ):
        execution_plan = replace(
            execution_plan,
            direct_answer=True,
            reasoning=(execution_plan.reasoning or "") + "（当前智能体无检索工具，改为直接作答）",
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            steps=(),
        )

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill

    plan_has_script = None
    if execution_plan.uploaded_skill:
        from app.services.agent_skill_service import uploaded_skill_has_script

        try:
            plan_has_script = uploaded_skill_has_script(db, execution_plan.uploaded_skill)
        except Exception:
            plan_has_script = None

    from app.services.agent_execution_closure import execution_plan_needs_skill_data

    if execution_plan_needs_skill_data(
        execution_plan, user_message, plan_has_script=plan_has_script
    ):
        loop_state["expects_skill_data"] = True

    from app.services.agent_planner import SKILL_MGMT_INTENT
    from app.services.agent_tool_search import register_unlocked_tools

    unlock_names: list[str] = []
    if execution_plan.uploaded_skill:
        unlock_names.append("run_skill_script")
    if execution_plan.intent == SKILL_MGMT_INTENT:
        unlock_names.extend(
            [
                "run_skill_script",
                "create_uploaded_skill",
                "update_uploaded_skill_file",
                "delete_uploaded_skill",
            ]
        )
    if unlock_names:
        register_unlocked_tools(loop_state, unlock_names)

    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "正在执行任务",
            "detail": execution_plan.summary_for_ui(),
            "tool": "agent.execute",
            "step_id": loop_id,
        },
    }

    if execution_plan.direct_answer:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        reply_parts: list[str] = []
        sess.release_before_io()
        async for ev in iter_llm_answer_events(
            messages=working,
            temperature=0.5,
            think_title="生成回答",
            think_detail=execution_plan.intent or "直接作答",
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
                "title": "执行完成",
                "detail": execution_plan.intent or "已生成回复",
                "tool": "agent.execute",
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

    from app.services.agent_execution_closure import (
        apply_execution_plan_unlocks,
        auto_execute_uploaded_skill,
        build_skill_management_continue_nudge,
        execution_goal_satisfied,
        execution_plan_needs_skill_data,
        max_adaptive_execution_passes,
        resolve_adaptive_replan,
        resolve_target_uploaded_skill,
        tool_rounds_for_adaptive_pass,
    )
    from app.services.agent_planner import _skill_name_sets

    _, uploaded_names = _skill_name_sets(db, user)
    max_adaptive = max_adaptive_execution_passes()
    deliverable_reply: str | None = None
    instruction_only_skill = plan_has_script is False and bool(
        execution_plan.uploaded_skill or loop_state.get("planned_uploaded_skill")
    )

    for adaptive_pass in range(max_adaptive):
        if adaptive_pass > 0:
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break
            prior_plan = execution_plan
            sess.release_before_io()
            execution_plan = await resolve_adaptive_replan(
                db,
                user,
                message=user_message,
                history=chat_history,
                intent_plan=intent_plan,
                available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
                kg_planning_context=kg_plan_text or None,
                prior_plan=prior_plan,
                loop_state=loop_state,
                uploaded_names=uploaded_names,
            )
            execution_plan = _narrow_execution_plan_for_specialist(
                execution_plan,
                agent_id=agent_id,
                allowed_skill_names=allowed_skill_names,
                user_message=user_message,
            )
            sess.release_before_io()
            db, user = sess.open()
            if execution_plan.uploaded_skill:
                from app.services.agent_skill_service import uploaded_skill_has_script

                try:
                    plan_has_script = uploaded_skill_has_script(
                        db, execution_plan.uploaded_skill
                    )
                except Exception:
                    plan_has_script = None
            apply_execution_plan_unlocks(execution_plan, loop_state)
            if execution_plan_needs_skill_data(
                execution_plan, user_message, plan_has_script=plan_has_script
            ):
                loop_state["expects_skill_data"] = True
            replan_instruction = build_plan_context_instruction(
                execution_plan,
                uploaded_skill_has_script=plan_has_script,
            )
            working = _inject_plan_instruction(working, replan_instruction)
            skill_for_md = str(execution_plan.uploaded_skill or "").strip()
            if skill_for_md:
                working = maybe_inject_skill_md(
                    db, user, loop_state, working, skill_for_md
                )
            instruction_only_skill = plan_has_script is False and bool(skill_for_md)
            loop_state["content_only_nudges"] = 0

        rounds_this_pass = tool_rounds_for_adaptive_pass(rounds, adaptive_pass)
        for _ in range(max(1, rounds_this_pass)):
            pending_skill = str(loop_state.get("pending_skill_md_inject") or "").strip()
            allowed_skills = loop_state.get("allowed_skill_names")
            if pending_skill and allowed_skills is not None and pending_skill not in allowed_skills:
                loop_state.pop("pending_skill_md_inject", None)
                pending_skill = ""
            if pending_skill:
                working = maybe_inject_skill_md(db, user, loop_state, working, pending_skill)
                loop_state.pop("pending_skill_md_inject", None)

            planned_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
            if allowed_tool_names is None:
                from app.services.agent_tool_search import select_visible_tool_specs

                unlocked = loop_state.get("unlocked_tools") or set()
                tool_specs = select_visible_tool_specs(planned_specs, unlocked)
            else:
                tool_specs = planned_specs
            keep_tools = 2 if is_skill_management_message(user_message) else 1
            llm_messages = trim_agent_loop_messages(
                inject_retrieval_context_message(working, loop_state),
                keep_full_tool_results=keep_tools,
            )
            sess.release_before_io()
            choice = await chat_completion_message_async(
                messages=llm_messages,
                tools=tool_specs or None,
                temperature=0.3,
            )
            db, user = sess.open()
            if not choice:
                break
            message = normalize_llm_assistant_message(choice.get("message") or {})
            tool_calls = message.get("tool_calls") or []
            content = strip_dsml_markup(str(message.get("content") or "")).strip()

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
                    from app.services.agent_admin_reply import (
                        capture_admin_list_deterministic_reply,
                    )

                    capture_admin_list_deterministic_reply(
                        db,
                        tool_name=tool_name,
                        result_text=result_text,
                        loop_state=loop_state,
                    )
                    if (
                        ok
                        and tool_name == ATOMIC_TOOL_KG_QUERY
                        and loop_state.get("kg_context")
                    ):
                        from app.services.kg_service import (
                            try_department_members_deterministic_reply,
                        )

                        if not loop_state.get("deterministic_reply"):
                            dept_reply = try_department_members_deterministic_reply(
                                db, user, user_message
                            )
                            if dept_reply:
                                loop_state["deterministic_reply"] = dept_reply
                            else:
                                kg_ctx = loop_state["kg_context"]
                                ctx_text = str(
                                    getattr(kg_ctx, "context_text", None)
                                    or (
                                        kg_ctx.get("context_text")
                                        if isinstance(kg_ctx, dict)
                                        else ""
                                    )
                                    or ""
                                ).strip()
                                if ctx_text:
                                    loop_state["deterministic_reply"] = ctx_text
                    outcome_lines = list(loop_state.get("tool_outcome_lines") or [])
                    outcome_lines.append(
                        f"{meta.get('title') or tool_name}：{summary or ('完成' if ok else '失败')}"
                    )
                    loop_state["tool_outcome_lines"] = outcome_lines[-12:]
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
                        _mark_streamed_attachment(loop_state, att)
                        yield {"type": "attachment", "data": att}
                    loop_state["stream_attachments"] = []
                if not execution_goal_satisfied(
                    execution_plan,
                    loop_state,
                    user_message,
                    plan_has_script=plan_has_script,
                ):
                    working.append(
                        {
                            "role": "system",
                            "content": build_skill_management_continue_nudge(
                                user_message, loop_state
                            ),
                        }
                    )
                    continue
                break

            if content:
                working.append({"role": "assistant", "content": content})
            if content and assistant_content_is_deliverable(
                content, instruction_only_skill=instruction_only_skill
            ):
                deliverable_reply = content.strip()
                if loop_state.get("report_write_mode"):
                    for ev in _emit_report_reply_deltas(deliverable_reply):
                        yield ev
                break
            has_outcomes = bool(
                loop_state.get("tool_outcome_lines")
                or loop_state.get("last_skill_conclusion")
            )
            nudges = int(loop_state.get("content_only_nudges") or 0)
            if not has_outcomes and nudges < 2:
                loop_state["content_only_nudges"] = nudges + 1
                raw_content = str((choice.get("message") or {}).get("content") or "")
                if loop_state.get("report_write_mode") and content_has_dsml_markup(
                    raw_content
                ):
                    nudge = (
                        "【系统】禁止在正文输出 DSML / tool_calls 标记。"
                        "必须通过 API tool_calls 调用 knowledge_retrieve、web_search、"
                        "load_uploaded_skill；content 留空即可。"
                    )
                elif instruction_only_skill:
                    nudge = (
                        "【系统】请按 SKILL.md 在回复正文中完成作答"
                        "（图表用 ```mermaid 围栏），勿调用 run_skill_script。"
                    )
                else:
                    from app.services.agent_skill_router import (
                        is_platform_system_data_message,
                    )

                    if is_platform_system_data_message(user_message):
                        nudge = (
                            "【系统】必须先调用 list_users（管理员）或 kg_query 获取真实数据；"
                            "禁止编造用户姓名、邮箱或部门。"
                        )
                    else:
                        if execution_plan.uploaded_skill and plan_has_script:
                            nudge = (
                                f"【系统】必须调用 run_skill_script(skill_name="
                                f"\"{execution_plan.uploaded_skill}\", args=...) 获取真实数据；"
                                "禁止在正文作答或让用户自行执行命令。"
                            )
                        else:
                            nudge = (
                                "【系统】请仅通过 tool_calls 完成任务；"
                                "勿在正文输出代码、调试细节或面向用户的总结。"
                            )
                working.append({"role": "system", "content": nudge})
                continue
            break

        if deliverable_reply:
            break

        if execution_goal_satisfied(
            execution_plan,
            loop_state,
            user_message,
            plan_has_script=plan_has_script,
        ):
            break

        skill = resolve_target_uploaded_skill(
            execution_plan=execution_plan,
            loop_state=loop_state,
            user_message=user_message,
            chat_history=chat_history,
            uploaded_names=uploaded_names,
        )
        if skill and plan_has_script is not False:
            closure_step = f"agent-closure-{uuid.uuid4().hex[:8]}"
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": "自动执行技能",
                    "detail": skill,
                    "tool": "agent.closure",
                    "step_id": closure_step,
                },
            }
            sess.release_before_io()
            _ok, _summary = await auto_execute_uploaded_skill(
                db,
                user,
                skill_name=skill,
                user_message=user_message,
                chat_history=chat_history,
                loop_state=loop_state,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
            )
            db, user = sess.open()
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "技能执行完成" if _ok else "技能执行未获有效数据",
                    "detail": _summary[:200] if _summary else "",
                    "tool": "agent.closure",
                    "step_id": closure_step,
                    "status": "done" if _ok else "failed",
                },
            }
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break

    sess.release_before_io()
    db, user = sess.open()
    await _maybe_auto_browser_screenshot(
        db,
        user,
        conversation_id=conversation_id,
        loop_state=loop_state,
        user_message=user_message,
    )
    for att in _pending_screenshot_attachments(loop_state):
        yield {"type": "attachment", "data": att}

    if deliverable_reply:
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "回答完成",
                "detail": "已按技能说明生成内容",
                "tool": "agent.direct",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": _finalize_loop_reply(deliverable_reply, loop_state),
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        return

    if loop_state.get("report_write_mode"):
        reply_parts: list[str] = []
        intent = str(loop_state.get("report_intent") or "initial")
        from app.services.report_generation_agent_service import iter_report_final_llm_events

        async for ev in iter_report_final_llm_events(
            working_messages=working,
            loop_state=loop_state,
            intent=intent,
        ):
            if ev.get("type") == "workflow":
                yield {"type": "workflow", "data": ev["data"]}
            elif ev.get("type") == "delta" and ev.get("text"):
                reply_parts.append(ev["text"])
                yield {"type": "delta", "text": ev["text"]}
        final_reply = "".join(reply_parts).strip() or None
        if final_reply:
            final_reply = strip_dsml_markup(final_reply) or None
        if final_reply:
            working.append({"role": "assistant", "content": final_reply})
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "报告撰写完成",
                "detail": "",
                "tool": "report.write",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": _finalize_loop_reply(final_reply, loop_state),
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        return

    if task_mode:
        handoff = build_specialist_handoff(
            loop_state,
            user_message,
            agent_id=(agent_id or "").strip(),
            session_id=(conversation_id or "").strip() or f"session-{loop_id}",
            task_id=(task_id or "").strip() or f"task-{loop_id}",
            citations=list(loop_state.get("citations") or []),
            kg_context=loop_state.get("kg_context"),
        )
        final_reply = handoff.text if handoff.ok else None
        if final_reply:
            working.append({"role": "assistant", "content": final_reply})
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "子任务完成" if handoff.ok else "子任务未完成",
                "detail": "",
                "tool": "agent.handoff",
                "step_id": loop_id,
                "status": "done" if handoff.ok else "failed",
            },
        }
        complete_payload: dict[str, Any] = {
            "type": "complete",
            "messages": working,
            "reply": _finalize_loop_reply(final_reply, loop_state),
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        yield attach_handoff_to_complete(complete_payload, handoff.message)
        return

    synth_id = f"agent-synth-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "整理最终回答",
            "detail": "",
            "tool": "agent.synthesize",
            "step_id": synth_id,
        },
    }
    from app.services.agent_memory_service import build_memory_prompt_context

    sess.release_before_io()
    final_reply = await synthesize_tool_loop_user_reply(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=build_memory_prompt_context(uid),
        chat_history=chat_history,
    )
    if final_reply:
        working.append({"role": "assistant", "content": final_reply})
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "执行完成",
            "detail": "已根据工具结果生成结论",
            "tool": "agent.execute",
            "step_id": loop_id,
            "status": "done",
        },
    }

    yield {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(final_reply or None, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }
