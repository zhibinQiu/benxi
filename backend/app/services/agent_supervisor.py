"""多智能体 Supervisor — 意图路由、子智能体上下文与 handoff。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from agentkit_aip.messaging import reply_text_from_complete
from agentkit_aip.orchestration import best_reply_from_hops, merge_hop_citations
from agentkit_orchestrate import (
    ORCH_TASK_RESULT as _ORCH_TASK_RESULT,
    iter_parallel_task_events,
    iter_task_event_parts,
)
from app.core.agent.routing import (
    infer_route_mode,
    is_routing_ambiguous,
    pick_route,
    plan_orchestrator_direct,
)
from app.core.agent.types import (
    ROUTE_REASONS,
    AgentRoute,
    AgentRoutePlan,
    RouteMode,
)
from app.core.agent_loop_session import AgentLoopSession, coerce_user_id
from app.core.agent_profiles import get_agent_profile, resolve_agent_title
from app.services.agent_profile_service import is_agent_enabled
from app.core.aip.session_bus import get_session_bus
from app.services.agent_aip_executor import (
    SpecialistExecutionContext,
    iter_builtin_specialist_hop,
    record_handoff_to_session,
)
from app.integrations.deepseek_client import is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    AgentToolPlan,
    needs_knowledge_retrieval,
)
from app.core.platform_assistant import (
    assistant_conclusion_source_priority,
    assistant_user_communication_style,
    orchestrator_failure_communication_rule,
)
from app.services.agent_memory_service import build_memory_prompt_context
from app.services.agent_orchestrator import (
    MAX_TASK_ATTEMPTS,
    OrchestratorAnswerAssessment,
    OrchestratorTask,
    TaskExecutionResult,
    append_screenshot_markdown_to_reply,
    append_supervisor_global_reflection,
    assess_orchestrator_answer_coverage,
    build_assist_resume_message,
    build_global_round_reflection,
    build_helper_assist_message,
    build_orchestrator_corrected_retry_message,
    build_skill_dev_escalation_message,
    collect_screenshot_attachments_from_task_results,
    extract_document_contexts_from_results,
    new_plan_step_id,
    new_task_step_id,
    resolve_assist_agent_id,
    should_escalate_to_skill_dev,
    supervisor_max_global_rounds,
    synthesize_specialist_correction_instruction,
    tasks_from_routes,
    verify_task_result,
    workflow_plan_tasks,
    workflow_task_event,
)
from app.config import get_settings
from app.core.aip.handoff import orchestrator_assist_from_complete
from app.services.agent_route_resolver import (
    resolve_agent_route,
    resolve_agent_route_plan,
    resolve_agent_routes,
    resolve_agent_routes_from_skills as _resolve_agent_routes,
)
from app.services.agent_runtime_service import mark_agent_idle, mark_agent_running

# 测试与旧代码兼容别名
_best_reply_from_hops = best_reply_from_hops
_logger = logging.getLogger(__name__)

_ROUTE_REASONS = ROUTE_REASONS
_pick_route = pick_route
_plan_orchestrator_direct = plan_orchestrator_direct
_is_routing_ambiguous = is_routing_ambiguous
_infer_route_mode = infer_route_mode

_HOP_CLIENT_PREVIEW_TYPES = frozenset({"replace", "delta"})
_ORCH_ROUND_RESULT = "_orchestrator_round_result"
_ORCH_ASSESSMENT_RESULT = "_orchestrator_assessment_result"
ORCH_TOOL_PROBE_ROUTE_MARKER = "__ROUTE__"


def _skip_hop_client_preview(event: dict[str, Any]) -> bool:
    """多智能体 hop 的中间回答仅用于 handoff，不下发前端（避免覆盖与二次闪烁）。"""
    return event.get("type") in _HOP_CLIENT_PREVIEW_TYPES


def _supervisor_max_global_rounds() -> int:
    return supervisor_max_global_rounds()


def _should_defer_orchestrator_synthesis(
    plan: AgentRoutePlan,
    *,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    max_global_rounds: int,
) -> bool:
    """全局 Loop 始终延后终稿：先验收子任务，再决定重跑或汇总。"""
    _ = (user_message, chat_history, max_global_rounds)
    return True


def _build_global_retry_context_instruction(
    base: str,
    reflection: str,
    *,
    global_round: int,
) -> str:
    block = (
        f"【调度全局反思 · 第 {global_round} 轮】\n"
        f"{reflection.strip()}\n\n"
        "请避免重复无效路径，补齐上述缺口后再交付。"
    )
    base_text = (base or "").strip()
    return f"{base_text}\n\n{block}".strip() if base_text else block


def _build_task_result_from_hop(
    route: AgentRoute,
    *,
    events: list[dict[str, Any]],
    complete: dict[str, Any] | None,
    task_id: str = "t1",
) -> TaskExecutionResult:
    profile = get_agent_profile(route.agent_id)
    title = profile.title if profile else route.agent_id
    task = OrchestratorTask(
        id=task_id,
        title=title,
        agent_id=route.agent_id,
        reason=route.reason,
    )
    satisfied, summary, retry_hint = verify_task_result(task, events, complete)
    if satisfied:
        task.status = "done"
        task.summary = summary
    else:
        task.status = "failed"
        task.last_error = retry_hint or "未能完成"
    return TaskExecutionResult(
        task=task,
        route=route,
        events=events,
        complete=complete,
        satisfied=satisfied,
    )


def _round_result_event(
    *,
    results: list[TaskExecutionResult],
    hop_completes: list[dict[str, Any] | None],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": _ORCH_ROUND_RESULT,
        "results": results,
        "hop_completes": hop_completes,
        "messages": messages,
    }


def _global_loop_iteration_workflow(global_round: int, max_rounds: int, detail: str) -> dict[str, Any]:
    step_id = f"supervisor-global-{uuid.uuid4().hex[:8]}"
    return {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": f"全局迭代 · 第 {global_round + 1}/{max_rounds} 轮",
            "detail": detail[:240],
            "tool": "supervisor.global_loop",
            "step_id": step_id,
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }


async def _try_orchestrator_tool_probe(
    user_id: uuid.UUID,
    messages: list[dict[str, Any]],
    *,
    user_message: str,
    conversation_id: str | None,
    chat_history: list[AiChatMessage] | None,
) -> AsyncIterator[dict[str, Any]]:
    """Orchestrator 工具探针：直接调 LLM + 工具，绕过 Planner，避免 direct_answer 问题。

    产出 workflow / complete 事件流。complete.reply 以 ORCH_TOOL_PROBE_ROUTE_MARKER
    开头表示工具不足以回答，需继续路由；否则为直接答案（含工具调用步骤）。
    """
    import json
    from app.core.agent_tool_context import compress_tool_result_for_loop
    from app.core.platform_assistant import (
        PLATFORM_AI_ASSISTANT_NAME,
        assistant_user_communication_style,
    )
    from app.core.routing_catalog_md import build_agents_catalog_text
    from app.integrations.deepseek_client import (
        chat_completion_stream_choice,
        is_configured,
    )
    from app.services.agent_planner import _skill_name_sets as _probe_skill_names
    from app.services.agent_profile_service import is_agent_enabled
    from app.services.agent_tools import build_agent_tool_specs, execute_agent_tool
    from app.services.agent_tool_loop import _parse_tool_summary

    if not is_configured():
        yield {
            "type": "complete",
            "messages": messages,
            "reply": ORCH_TOOL_PROBE_ROUTE_MARKER,
            "citations": [],
        }
        return

    msg = (user_message or "").strip()
    if not msg:
        yield {
            "type": "complete",
            "messages": messages,
            "reply": ORCH_TOOL_PROBE_ROUTE_MARKER,
            "citations": [],
        }
        return

    # 仅暴露检索类工具
    tool_names = {"web_search", "knowledge_retrieve", "kg_query"}

    sess = AgentLoopSession(user_id)
    try:
        db, user = sess.open()
        tool_specs = build_agent_tool_specs(db, user, allowed_names=tool_names)

        # 专精智能体目录 + 上传技能列表
        from app.core.agent_profiles import AGENT_PROFILES

        enabled_ids = frozenset(
            p.id
            for p in AGENT_PROFILES
            if p.id != "orchestrator" and is_agent_enabled(db, p.id)
        )
        agents_catalog = build_agents_catalog_text(enabled_ids=enabled_ids)
        upload_names = _probe_skill_names(db, user)
        skills_hint = "、".join(sorted(upload_names)) if upload_names else "暂无"
    except Exception:
        sess.close()
        yield {
            "type": "complete",
            "messages": messages,
            "reply": ORCH_TOOL_PROBE_ROUTE_MARKER,
            "citations": [],
        }
        return
    finally:
        sess.release_before_io()

    probe_prompt = (
        f"你是「{PLATFORM_AI_ASSISTANT_NAME}」，本析平台的智能助手，企业级对话入口。\n\n"
        "【你的能力概览】\n"
        "你可以直接使用以下工具快速回答用户问题：\n"
        "- web_search：联网搜索最新公开信息（天气、新闻、政策、价格、百科、实时数据等）\n"
        "- knowledge_retrieve：知识库检索企业内部资料、制度文档、知识片段\n"
        "- kg_query：本体图谱查询实体关系、组织架构\n\n"
        "如果工具无法解决，你可以将任务分配给以下专精智能体：\n"
        f"{agents_catalog}\n\n"
        f"可调用的技能包：{skills_hint}\n\n"
        "工作流程：\n"
        "1. 判断用户需求是否能通过联网/知识库/图谱工具直接满足\n"
        "2. 如果能，选最合适的工具获取信息，整理成清晰答案，注明信息来源\n"
        "3. 如果工具信息不足，或用户明确指定了专精智能体/技能名称，\n"
        f"   在回答最开头输出「{ORCH_TOOL_PROBE_ROUTE_MARKER}」表示需进一步路由\n\n"
        f"{assistant_user_communication_style()}"
    )

    # 构建对话消息
    working: list[dict[str, Any]] = [
        {"role": "system", "content": probe_prompt},
    ]
    if chat_history:
        for h in chat_history[-6:]:
            if h.role in ("user", "assistant"):
                working.append({"role": h.role, "content": h.content})
    if (
        not working
        or working[-1].get("role") != "user"
        or working[-1].get("content") != msg
    ):
        working.append({"role": "user", "content": msg})

    loop_id = f"orch-probe-{uuid.uuid4().hex[:8]}"
    cited_kg: dict | None = None

    # 最多 2 轮：第 1 轮调工具，第 2 轮汇总
    for probe_round in range(2):
        db, user = sess.open()
        try:
            choice = None
            async for ev in chat_completion_stream_choice(
                messages=working,
                tools=tool_specs if probe_round == 0 else None,
                temperature=0.3,
            ):
                if ev["type"] == "delta":
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "thinking_delta",
                            "delta": ev["text"],
                            "agent_id": "orchestrator",
                            "agent_title": "小析调度",
                        },
                    }
                elif ev["type"] == "choice":
                    choice = ev
            if not choice:
                break

            msg_obj = choice.get("message") or {}
            content = (msg_obj.get("content") or "").strip()
            tool_calls = msg_obj.get("tool_calls") or []

            # LLM 直接回答（含 __ROUTE__ 标记）
            if not tool_calls:
                yield {
                    "type": "complete",
                    "messages": working,
                    "reply": content,
                    "citations": [],
                    "kg_context": cited_kg,
                }
                return

            # 执行工具调用
            for tc in tool_calls:
                fn = tc.get("function") or {}
                tool_name = str(fn.get("name") or "")
                tool_id = str(tc.get("id") or uuid.uuid4())
                raw_args = fn.get("arguments") or "{}"
                step_id = f"probe-tool-{uuid.uuid4().hex[:8]}"

                # 提取查询参数用于展示
                try:
                    parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except (json.JSONDecodeError, TypeError):
                    parsed = {}
                q = str(
                    parsed.get("query")
                    or parsed.get("question")
                    or ""
                )[:120] or "(参数)"

                if tool_name == "web_search":
                    title = "联网搜索"
                elif tool_name == "knowledge_retrieve":
                    title = "知识库检索"
                elif tool_name == "kg_query":
                    title = "本体图谱查询"
                else:
                    title = tool_name

                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "tool_call",
                        "title": title,
                        "detail": q,
                        "tool": tool_name,
                        "step_id": step_id,
                        "agent_id": "orchestrator",
                        "agent_title": "小析调度",
                    },
                }

                result_text = await execute_agent_tool(
                    db,
                    user,
                    tool_name=tool_name,
                    arguments=raw_args,
                    conversation_id=conversation_id,
                    user_message=msg,
                    loop_state=None,
                )
                ok, summary = _parse_tool_summary(result_text)

                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "tool_result",
                        "title": f"{title}完成",
                        "detail": summary or ("完成" if ok else "失败"),
                        "tool": tool_name,
                        "step_id": step_id,
                        "status": "done" if ok else "failed",
                        "agent_id": "orchestrator",
                        "agent_title": "小析调度",
                    },
                }

                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": compress_tool_result_for_loop(result_text),
                    }
                )
        finally:
            sess.release_before_io()

    sess.close()

    # 超 2 轮仍未返回 → 路由
    yield {
        "type": "complete",
        "messages": working,
        "reply": ORCH_TOOL_PROBE_ROUTE_MARKER,
        "citations": [],
        "kg_context": cited_kg,
    }


async def _run_specialist_hop(
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    *,
    route: AgentRoute,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    task_mode: bool = False,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """执行单次专精 hop（委托 AIP 执行层）。"""
    ctx = SpecialistExecutionContext(
        agent_id=route.agent_id,
        user_message=user_message,
        session_id=(conversation_id or "").strip() or f"session-{uuid.uuid4().hex[:8]}",
        task_id=(task_id or "").strip() or f"task-{uuid.uuid4().hex[:8]}",
        reason=route.reason,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=task_mode,
    )
    conv_key = ctx.session_id
    mark_agent_running(route.agent_id, conv_key)
    try:
        async for event in iter_builtin_specialist_hop(sess, user_id, ctx):
            yield event
    finally:
        mark_agent_idle(route.agent_id, conv_key)


def _build_final_complete(
    *,
    messages: list[dict[str, Any]],
    hop_completes: list[dict[str, Any] | None],
    reply: str | None,
) -> dict[str, Any]:
    citation_lists = [
        list((ev or {}).get("citations") or []) for ev in hop_completes if ev
    ]
    kg_context = None
    for ev in reversed(hop_completes):
        if ev and ev.get("kg_context") is not None:
            kg_context = ev.get("kg_context")
            break
    last_messages = messages
    for ev in reversed(hop_completes):
        if ev and ev.get("messages"):
            last_messages = ev["messages"]
            break
    return {
        "type": "complete",
        "messages": last_messages,
        "reply": reply,
        "citations": merge_hop_citations(citation_lists),
        "kg_context": kg_context,
    }


def _agent_title(agent_id: str) -> str:
    return resolve_agent_title(agent_id)


def _build_orchestrator_synthesis_payload(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    screenshot_attachments: list[dict[str, Any]] | None = None,
    answer_assessment: OrchestratorAnswerAssessment | None = None,
) -> dict[str, Any]:
    lines: list[str] = []
    for item in results:
        task = item.task
        if item.satisfied and task.summary:
            lines.append(f"- {task.title}：{task.summary}")
        elif not item.satisfied:
            err = (task.last_error or "未能完成").strip()
            lines.append(f"- {task.title}（未完成）：{err}")

    doc_contexts = extract_document_contexts_from_results(results)
    doc_block = ""
    if doc_contexts:
        parts: list[str] = []
        for ctx in doc_contexts[:2]:
            title = str(ctx.get("title") or "文档").strip()
            text = str(ctx.get("full_text") or "").strip()[:12000]
            if text:
                parts.append(f"【{title}】\n{text}")
        if parts:
            doc_block = "\n\n参考文档正文：\n" + "\n\n".join(parts)

    shot_lines = [
        f"- 页面截图：{str(att.get('url') or '').strip()}"
        for att in list(screenshot_attachments or [])
        if str(att.get("url") or "").strip()
    ]

    assessment_block = ""
    if answer_assessment and not answer_assessment.addresses_user:
        gap = (answer_assessment.gap or answer_assessment.reason or "").strip()
        assessment_block = (
            "\n\n【调度验收 · 未充分回应用户诉求】"
            + (f"缺口：{gap}。" if gap else "")
            + "请基于下方证据尽可能回答用户；若已提供文档正文，应据此归纳总结，"
            "不可仅复述读取字数或工具状态。"
            "勿向用户说「任务失败/无法完成」；说明具体缺口与用户可采取的下一步。"
        )

    fallback = "\n".join(lines)
    if shot_lines:
        fallback += "\n\n【页面截图】\n" + "\n".join(shot_lines)

    return {
        "lines": lines,
        "doc_block": doc_block,
        "assessment_block": assessment_block,
        "shot_lines": shot_lines,
        "fallback": fallback,
        "hop_reply": best_reply_from_hops(
            [item.complete for item in results if item.complete]
        ),
    }


def _build_orchestrator_synthesis_messages(
    payload: dict[str, Any],
    *,
    user_message: str,
    memory_context: str = "",
) -> list[dict[str, str]]:
    from app.core.loop_engineering import build_loop_exit_prompt_messages

    shot_instruction = ""
    shot_lines = list(payload.get("shot_lines") or [])
    if shot_lines:
        shot_instruction = (
            "【截图要求】用户要求查看页面截图；请在答复末尾保留以下 URL：\n"
            + "\n".join(shot_lines)
        )
    extra = (
        f"【子任务结果】\n" + "\n".join(payload.get("lines") or [])
        + str(payload.get("doc_block") or "")
        + str(payload.get("assessment_block") or "")
        + shot_instruction
    )
    return build_loop_exit_prompt_messages(
        user_message=user_message,
        loop_state=None,
        memory_context=memory_context,
        extra_evidence=extra.strip(),
    )


async def _iter_orchestrator_synthesis_events(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
    screenshot_attachments: list[dict[str, Any]] | None = None,
    answer_assessment: OrchestratorAnswerAssessment | None = None,
    step_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    from app.services.llm_workflow_stream import iter_llm_answer_events

    payload = _build_orchestrator_synthesis_payload(
        user_message,
        results,
        screenshot_attachments=screenshot_attachments,
        answer_assessment=answer_assessment,
    )
    if not payload["lines"]:
        hop = str(payload.get("hop_reply") or "").strip()
        if hop:
            yield {"type": "complete_text", "text": hop}
        else:
            yield {"type": "complete_text", "text": ""}
        return

    if not is_configured():
        yield {"type": "complete_text", "text": str(payload.get("fallback") or "")}
        return

    messages = _build_orchestrator_synthesis_messages(
        payload,
        user_message=user_message,
        memory_context=memory_context,
    )
    try:
        async for ev in iter_llm_answer_events(
            messages=messages,
            temperature=0.4,
            think_title="汇总最终回答",
            think_detail="合并各子任务结果",
            step_id=step_id,
            skip_initial_thinking=True,
        ):
            yield ev
    except Exception:
        _logger.exception("任务结果汇总失败")
        yield {"type": "complete_text", "text": str(payload.get("fallback") or "")}


async def _synthesize_from_task_results(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
    screenshot_attachments: list[dict[str, Any]] | None = None,
    answer_assessment: OrchestratorAnswerAssessment | None = None,
) -> str:
    """根据各子任务验收摘要生成唯一最终回答。"""
    parts: list[str] = []
    async for ev in _iter_orchestrator_synthesis_events(
        user_message,
        results,
        memory_context=memory_context,
        screenshot_attachments=screenshot_attachments,
        answer_assessment=answer_assessment,
    ):
        if ev.get("type") == "delta" and ev.get("text"):
            parts.append(str(ev["text"]))
        elif ev.get("type") == "complete_text":
            text = str(ev.get("text") or "").strip()
            if text:
                return text
    merged = "".join(parts).strip()
    if merged:
        return merged
    payload = _build_orchestrator_synthesis_payload(
        user_message,
        results,
        screenshot_attachments=screenshot_attachments,
        answer_assessment=answer_assessment,
    )
    return str(payload.get("fallback") or payload.get("hop_reply") or "")


def _try_orchestrator_final_reply_fast_path(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    answer_assessment: OrchestratorAnswerAssessment | None = None,
    screenshot_attachments: list[dict[str, Any]] | None = None,
) -> str | None:
    from app.services.agent_skill_router import (
        is_org_member_list_question,
        is_platform_system_data_message,
        user_wants_browser_screenshot,
    )

    hop_reply = best_reply_from_hops(
        [item.complete for item in results if item.complete and item.satisfied]
    )
    assessment_ok = answer_assessment is None or answer_assessment.addresses_user
    shots = list(screenshot_attachments or [])

    if assessment_ok and hop_reply and (
        is_org_member_list_question(user_message)
        or is_platform_system_data_message(user_message)
    ):
        return append_screenshot_markdown_to_reply(hop_reply, shots)

    if assessment_ok and shots and user_wants_browser_screenshot(user_message):
        body = (hop_reply or "").strip() or "已完成您要求的浏览器操作，页面截图如下。"
        return append_screenshot_markdown_to_reply(body, shots)

    return None


def _chunk_stream_deltas(text: str, *, chunk_size: int = 600) -> list[dict[str, str]]:
    body = (text or "").strip()
    if not body:
        return []
    return [{"type": "delta", "text": body[i : i + chunk_size]} for i in range(0, len(body), chunk_size)]


async def _build_orchestrator_final_reply(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
    answer_assessment: OrchestratorAnswerAssessment | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """构建编排终稿：验收通过时可走 fast path；否则强制汇总并带缺口说明。"""
    screenshot_attachments = collect_screenshot_attachments_from_task_results(results)
    fast = _try_orchestrator_final_reply_fast_path(
        user_message,
        results,
        answer_assessment=answer_assessment,
        screenshot_attachments=screenshot_attachments,
    )
    if fast is not None:
        return fast, screenshot_attachments

    final_reply = await _synthesize_from_task_results(
        user_message,
        results,
        memory_context=memory_context,
        screenshot_attachments=screenshot_attachments,
        answer_assessment=answer_assessment,
    )
    final_reply = append_screenshot_markdown_to_reply(
        final_reply, screenshot_attachments
    )
    return final_reply, screenshot_attachments


async def _iter_one_orchestrated_task(
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    task: OrchestratorTask,
    route: AgentRoute,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    conv_key: str,
    all_tasks: list[OrchestratorTask],
) -> AsyncIterator[dict[str, Any]]:
    """执行单个子任务（含重试），实时产出 workflow 事件。"""
    step_id = new_task_step_id(task.id)
    yield workflow_task_event("task_started", task, step_id=step_id, all_tasks=all_tasks)
    task.status = "running"

    satisfied = False
    events: list[dict[str, Any]] = []
    complete: dict[str, Any] | None = None
    attempt_message = user_message
    correction_for_retry = ""

    for attempt in range(1, MAX_TASK_ATTEMPTS + 1):
        task.attempts = attempt
        if attempt > 1:
            yield workflow_task_event(
                "task_retry",
                task,
                step_id=step_id,
                detail=correction_for_retry or task.last_error,
                attempt=attempt,
                all_tasks=all_tasks,
            )
            # 更新所有任务的尝试信息
            for t in all_tasks:
                t.attempts = attempt
            attempt_message = build_orchestrator_corrected_retry_message(
                user_message,
                task,
                correction_for_retry or task.last_error,
            )

        mark_agent_running(route.agent_id, conv_key)
        hop_events: list[dict[str, Any]] = []
        try:
            async for event in _run_specialist_hop(
                sess,
                user_id,
                route=route,
                user_message=attempt_message,
                chat_history=chat_history,
                retrieval_context=retrieval_context,
                context_instruction=context_instruction,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                task_mode=True,
                task_id=task.id,
            ):
                if event.get("type") == "complete":
                    complete = event
                else:
                    hop_events.append(event)
                    if not _skip_hop_client_preview(event):
                        yield event
        finally:
            mark_agent_idle(route.agent_id, conv_key)

        events = hop_events
        assist_req = orchestrator_assist_from_complete(complete)
        if assist_req:
            satisfied = False
            task.last_error = str(assist_req.get("reason") or "需调度协助").strip()
            task.status = "running"
            break
        satisfied, summary, retry_hint = verify_task_result(task, events, complete)
        if satisfied:
            task.status = "done"
            task.summary = summary
            yield workflow_task_event(
                "task_done",
                task,
                step_id=step_id,
                detail=summary,
                all_tasks=all_tasks,
            )
            break
        task.last_error = retry_hint or "未能完成该步骤"
        db, bound_user = sess.open()
        try:
            memory_context = build_memory_prompt_context(bound_user.id)
        finally:
            sess.release_before_io()
        correction_for_retry = await synthesize_specialist_correction_instruction(
            user_message=user_message,
            task=task,
            events=events,
            complete=complete,
            rule_hint=task.last_error,
            memory_context=memory_context,
        )
        task.correction_instruction = correction_for_retry
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "调度改正指引",
                "detail": correction_for_retry[:240],
                "tool": "supervisor.correct",
                "step_id": f"supervisor-correct-{uuid.uuid4().hex[:8]}",
                "status": "done",
                "agent_id": "orchestrator",
                "agent_title": "小析调度",
                "task_id": task.id,
            },
        }
        task.status = "running"

    if not satisfied:
        task.status = "failed"
        yield workflow_task_event(
            "task_failed",
            task,
            step_id=step_id,
            detail=task.last_error,
            all_tasks=all_tasks,
        )

    aip_handoff = record_handoff_to_session(conv_key, complete)

    yield {
        "type": _ORCH_TASK_RESULT,
        "result": TaskExecutionResult(
            task=task,
            route=route,
            events=events,
            complete=complete,
            satisfied=satisfied,
            aip_handoff=aip_handoff,
        ),
    }


async def _iter_task_with_scheduler_assist(
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    task: OrchestratorTask,
    route: AgentRoute,
    hop_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    conv_key: str,
    all_tasks: list[OrchestratorTask],
    user_message: str,
    use_shared_history: bool,
) -> AsyncIterator[dict[str, Any]]:
    """单任务执行 + 调度层协助专精 + 交还原专精续办（星型编排）。"""
    settings = get_settings()
    max_assist = max(0, int(settings.agent_orchestrator_max_assist_rounds or 2))

    current_message = hop_message
    final_result: TaskExecutionResult | None = None

    for assist_idx in range(max_assist + 1):
        hop_history = chat_history if (use_shared_history and assist_idx == 0) else None
        hop_retrieval = retrieval_context if assist_idx == 0 else ""
        hop_context = context_instruction if assist_idx == 0 else ""

        result: TaskExecutionResult | None = None
        async for kind, payload in iter_task_event_parts(
            _iter_one_orchestrated_task(
                sess=sess,
                user_id=user_id,
                task=task,
                route=route,
                user_message=current_message,
                chat_history=hop_history,
                retrieval_context=hop_retrieval,
                context_instruction=hop_context,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                conv_key=conv_key,
                all_tasks=all_tasks,
            )
        ):
            match kind:
                case "event":
                    yield payload
                case "result":
                    result = payload

        if result is None:
            return
        final_result = result
        if result.satisfied or assist_idx >= max_assist:
            break

        assist = orchestrator_assist_from_complete(result.complete)
        if not assist:
            break

        helper_id = resolve_assist_agent_id(
            assist,
            result.task,
            user_message,
            events=result.events,
        )
        if not helper_id or helper_id == route.agent_id:
            break

        helper_task = OrchestratorTask(
            id=f"{task.id}-h{assist_idx + 1}",
            title=resolve_agent_title(helper_id),
            agent_id=helper_id,
            reason=f"调度协助 · {task.title}",
        )
        all_tasks.append(helper_task)
        helper_route = AgentRoute(agent_id=helper_id, reason=helper_task.reason)
        helper_message = build_helper_assist_message(user_message, task, assist)

        helper_result: TaskExecutionResult | None = None
        async for kind, payload in iter_task_event_parts(
            _iter_one_orchestrated_task(
                sess=sess,
                user_id=user_id,
                task=helper_task,
                route=helper_route,
                user_message=helper_message,
                chat_history=None,
                retrieval_context="",
                context_instruction="",
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                conv_key=conv_key,
                all_tasks=all_tasks,
            )
        ):
            match kind:
                case "event":
                    yield payload
                case "result":
                    helper_result = payload

        if not helper_result or not helper_result.satisfied:
            break

        helper_summary = helper_result.task.summary or ""
        if not helper_summary and helper_result.complete:
            helper_summary = reply_text_from_complete(helper_result.complete)[:400]

        current_message = build_assist_resume_message(
            session_id=conv_key,
            task_id=task.id,
            target_agent_id=route.agent_id,
            user_message=user_message,
            helper_title=helper_task.title,
            helper_summary=helper_summary,
        )
        task.status = "running"
        task.last_error = ""
        task.attempts = 0

    if final_result is not None:
        yield {"type": _ORCH_TASK_RESULT, "result": final_result}


async def _iter_skill_dev_escalation(
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    parent_task: OrchestratorTask,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    conv_key: str,
    all_tasks: list[OrchestratorTask],
) -> AsyncIterator[dict[str, Any]]:
    """专精未满足且像能力缺口时，调度层追加 skill-dev 子任务。"""
    db, _user = sess.open()
    try:
        if not is_agent_enabled(db, "skill-dev"):
            return
    finally:
        sess.release_before_io()

    esc_task = OrchestratorTask(
        id=f"{parent_task.id}-skill",
        title="发展技能补能力",
        agent_id="skill-dev",
        reason="平台缺能力，创建或执行 Skill 以满足诉求",
    )
    all_tasks.append(esc_task)
    esc_route = AgentRoute(agent_id="skill-dev", reason=esc_task.reason)
    esc_message = build_skill_dev_escalation_message(user_message, parent_task)

    async for event in _iter_one_orchestrated_task(
        sess=sess,
        user_id=user_id,
        task=esc_task,
        route=esc_route,
        user_message=esc_message,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        conv_key=conv_key,
        all_tasks=all_tasks,
    ):
        yield event


async def _execute_auto_skill_dev_task(
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    route: AgentRoute,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """自动 Skill 创建任务：让 skill-dev 创建、验证并返回结果（defer_synthesis 模式）。"""
    task = OrchestratorTask(
        id=f"auto-skill-{uuid.uuid4().hex[:8]}",
        title="自动创建发展技能",
        agent_id="skill-dev",
        reason=route.reason,
    )
    hop_events: list[dict[str, Any]] = []
    complete: dict[str, Any] | None = None
    auto_message = (
        f"{user_message.strip()}\n\n"
        f"【调度自动补能力】{context_instruction.strip()}"
    ).strip()
    async for event in _run_specialist_hop(
        sess,
        user_id,
        route=route,
        user_message=auto_message,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=True,
        task_id=task.id,
    ):
        if event.get("type") == "complete":
            complete = event
            continue
        hop_events.append(event)
        if not _skip_hop_client_preview(event):
            yield event
    result = _build_task_result_from_hop(route, events=hop_events, complete=complete, task_id=task.id)
    yield _round_result_event(
        results=[result],
        hop_completes=[complete],
        messages=(complete or {}).get("messages") or messages,
    )


async def _execute_auto_skill_dev_task_interactive(
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    route: AgentRoute,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
) -> AsyncIterator[dict[str, Any]]:
    """自动 Skill 创建任务：交互式直接输出（非 defer_synthesis 模式）。"""
    task = OrchestratorTask(
        id=f"auto-skill-{uuid.uuid4().hex[:8]}",
        title="自动创建发展技能",
        agent_id="skill-dev",
        reason=route.reason,
    )
    auto_message = (
        f"{user_message.strip()}\n\n"
        f"【调度自动补能力】{context_instruction.strip()}"
    ).strip()
    async for event in _run_specialist_hop(
        sess,
        user_id,
        route=route,
        user_message=auto_message,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=True,
        task_id=task.id,
    ):
        yield event


# ─── 调度端后台并发执行 + 进度事件交织 ──────────────────────────


def _orchestrator_progress_event(
    *,
    detail: str,
    step_id: str | None = None,
) -> dict[str, Any]:
    """调度端进度事件——表示调度正在工作中而非等待子任务完成。"""
    return {
        "type": "workflow",
        "data": {
            "phase": "orchestrator_progress",
            "title": "调度执行中",
            "detail": detail,
            "tool": "supervisor.progress",
            "step_id": step_id or f"orch-progress-{uuid.uuid4().hex[:8]}",
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }


async def _execute_tasks_with_orchestrator_progress(
    subagent_generator,
    *,
    agent_titles: list[str],
    progress_interval: float = 2.5,
) -> AsyncIterator[dict[str, Any]]:
    """包装子任务流，在后台任务运行时交织调度端进度事件。

    所有子智能体同时在后台运行，调度器不阻塞等待，而是周期性发送
    orchestrator_progress 事件，让前端看到调度仍在工作。
    """
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=200)
    total = len(agent_titles)
    completed = 0
    results: list[Any] = []

    async def _subagent_forwarder():
        nonlocal completed, results
        async for event in subagent_generator:
            await queue.put(("event", event))
        await queue.put(("_done", None))

    forward_task = asyncio.create_task(_subagent_forwarder())

    async def _progress_emitter():
        while True:
            await asyncio.sleep(progress_interval)
            running = agent_titles[completed:]
            if not running:
                continue
            try:
                detail = f"调度中 · {'、'.join(running)} · {completed}/{total}"
                await queue.put(("progress", _orchestrator_progress_event(detail=detail)))
            except asyncio.QueueFull:
                pass

    progress_task = asyncio.create_task(_progress_emitter())

    try:
        while True:
            kind, payload = await queue.get()
            if kind == "_done":
                break
            elif kind == "event":
                yield payload
            elif kind == "progress":
                yield payload
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass


async def _execute_orchestrated_tasks(
    routes: list[AgentRoute],
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    messages: list[dict[str, Any]],
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    mode: str = "sequential",
    skip_plan_ui: bool = False,
    defer_synthesis: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """子任务编排：可选任务清单 → 专精执行 → 调度汇总答复用户。"""
    conv_key = (conversation_id or "").strip() or f"ephemeral-{uuid.uuid4().hex[:8]}"
    tasks = tasks_from_routes(routes)
    all_tasks: list[OrchestratorTask] = list(tasks)
    plan_id = new_plan_step_id()
    bus = get_session_bus()
    bus.reset(conv_key)
    if not skip_plan_ui:
        yield workflow_plan_tasks(tasks, step_id=plan_id, mode=mode)

    if mode == "parallel":
        async for event in _execute_parallel_task_workers(
            routes,
            tasks=tasks,
            all_tasks=all_tasks,
            user_id=user_id,
            messages=messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            retrieval_context=retrieval_context,
            context_instruction=context_instruction,
            conv_key=conv_key,
            defer_synthesis=defer_synthesis,
        ):
            yield event
        return

    results: list[TaskExecutionResult] = []
    hop_completes: list[dict[str, Any] | None] = []
    hop_message = user_message
    total_tasks = len(tasks)

    # 串行执行开始：调度端发射规划信息
    if total_tasks > 1:
        agent_titles = [resolve_agent_title(r.agent_id) for r in routes]
        yield _orchestrator_progress_event(
            detail=f"调度计划 · 按序执行 {' → '.join(agent_titles)}（共 {total_tasks} 个）",
        )

    for task_idx, (task, route) in enumerate(zip(tasks, routes)):
        # 每步开始前发射调度进度，让前端知道调度器在工作
        if task_idx > 0:
            done_agents = [resolve_agent_title(r.agent_id) for r in routes[:task_idx]]
            next_agent = resolve_agent_title(route.agent_id)
            yield _orchestrator_progress_event(
                detail=f"✔ {'、'.join(done_agents)} 已完成 · 下一步：{next_agent}（{task_idx}/{total_tasks}）",
            )

            hop_message = bus.format_task_request_for_llm(
                session_id=conv_key,
                task_id=task.id,
                target_agent_id=route.agent_id,
                user_message=user_message,
            )

        result: TaskExecutionResult | None = None
        async for kind, payload in iter_task_event_parts(
            _iter_task_with_scheduler_assist(
                sess=sess,
                user_id=user_id,
                task=task,
                route=route,
                hop_message=hop_message,
                chat_history=chat_history,
                retrieval_context=retrieval_context if task_idx == 0 else "",
                context_instruction=context_instruction if task_idx == 0 else "",
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                conv_key=conv_key,
                all_tasks=all_tasks,
                user_message=user_message,
                use_shared_history=(task_idx == 0),
            )
        ):
            match kind:
                case "event":
                    yield payload
                case "result":
                    result = payload
        if result is not None:
            results.append(result)
            escalate = (
                not result.satisfied
                and should_escalate_to_skill_dev(
                    result.task,
                    satisfied=result.satisfied,
                    events=result.events,
                )
            )
            if escalate:
                async for kind, payload in iter_task_event_parts(
                    _iter_skill_dev_escalation(
                        sess=sess,
                        user_id=user_id,
                        parent_task=result.task,
                        user_message=user_message,
                        chat_history=chat_history,
                        retrieval_context=retrieval_context if task_idx == 0 else "",
                        context_instruction=context_instruction if task_idx == 0 else "",
                        conversation_id=conversation_id,
                        attachment_session_id=attachment_session_id,
                        tools=tools,
                        intent_plan=intent_plan,
                        max_rounds=max_rounds,
                        conv_key=conv_key,
                        all_tasks=all_tasks,
                    )
                ):
                    match kind:
                        case "event":
                            yield payload
                        case "result":
                            esc = payload
                            if esc.satisfied:
                                results.append(esc)
        if result and result.complete:
            hop_completes.append(result.complete)

    if defer_synthesis:
        yield _round_result_event(
            results=results,
            hop_completes=hop_completes,
            messages=messages,
        )
        return

    async for event in _yield_orchestrator_synthesis(
        user_message,
        results,
        user_id=user_id,
        messages=messages,
        hop_completes=hop_completes,
    ):
        yield event


async def _execute_parallel_task_workers(
    routes: list[AgentRoute],
    *,
    tasks: list[OrchestratorTask],
    user_id: uuid.UUID,
    messages: list[dict[str, Any]],
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conv_key: str,
    defer_synthesis: bool = False,
    all_tasks: list[OrchestratorTask] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """并行执行各子任务，合并事件流，交织调度进度事件。

    所有子智能体同时在后台运行，调度器不阻塞等待，而是持续发送
    orchestrator_progress 事件让前端看到调度端仍在工作。
    """
    snapshot = all_tasks or tasks
    agent_titles = [resolve_agent_title(r.agent_id) for r in routes]
    total = len(routes)

    async def _run_one(sess, *, task, route, **kw):
        async for event in _iter_one_orchestrated_task(sess=sess, task=task, route=route, **kw):
            yield event

    # 用 asyncio.Queue 合并子任务流与调度进度事件
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=500)

    async def _forward_subagent_events():
        async for kind, payload in iter_parallel_task_events(
            tasks,
            routes,
            session_factory=lambda: AgentLoopSession(user_id),
            run_one_task=_run_one,
            all_tasks=snapshot,
            agent_title_fn=resolve_agent_title,
            close_session=AgentLoopSession.close,
            user_id=user_id,
            user_message=user_message,
            chat_history=chat_history,
            retrieval_context=retrieval_context,
            context_instruction=context_instruction,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            max_rounds=max_rounds,
            conv_key=conv_key,
        ):
            await queue.put((kind, payload))
        await queue.put(("_done", None))

    forward_task = asyncio.create_task(_forward_subagent_events())

    # 调度进度事件发射器——周期发送，表示调度在工作中
    completed_count = 0

    async def _progress_emitter():
        while True:
            await asyncio.sleep(2.5)
            running = agent_titles[completed_count:]
            if not running:
                continue
            try:
                detail = f"调度中 · {'、'.join(running)} · {completed_count}/{total}"
                await queue.put(("progress", _orchestrator_progress_event(detail=detail)))
            except asyncio.QueueFull:
                pass

    progress_task = asyncio.create_task(_progress_emitter())

    results: list[TaskExecutionResult] = []
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "_done":
                break
            elif kind == "event":
                yield payload
            elif kind == "result":
                results.append(payload)
                completed_count += 1
            elif kind == "progress":
                yield payload
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

    hop_completes = [r.complete for r in results if r.complete]
    if defer_synthesis:
        yield _round_result_event(
            results=results,
            hop_completes=hop_completes,
            messages=messages,
        )
        return
    async for event in _yield_orchestrator_synthesis(
        user_message,
        results,
        user_id=user_id,
        messages=messages,
        hop_completes=hop_completes,
    ):
        yield event


async def _yield_orchestrator_assessment_events(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    user_id: int,
) -> AsyncIterator[dict[str, Any]]:
    memory_context = build_memory_prompt_context(user_id)
    assess_id = f"agent-assess-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "验收用户诉求",
            "detail": "判断子任务交付是否已回应用户问题",
            "tool": "supervisor.assess",
            "step_id": assess_id,
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }
    answer_assessment = await assess_orchestrator_answer_coverage(
        user_message,
        results,
        memory_context=memory_context,
    )
    assess_detail = (
        "已回应用户诉求"
        if answer_assessment.addresses_user
        else (answer_assessment.gap or answer_assessment.reason or "尚未充分回应")
    )[:240]
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "验收完成",
            "detail": assess_detail,
            "tool": "supervisor.assess",
            "step_id": assess_id,
            "status": "done" if answer_assessment.addresses_user else "failed",
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }
    yield {"type": _ORCH_ASSESSMENT_RESULT, "assessment": answer_assessment}


async def _yield_orchestrator_synthesis(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    user_id: int,
    messages: list[dict[str, Any]],
    hop_completes: list[dict[str, Any] | None],
    answer_assessment: OrchestratorAnswerAssessment | None = None,
) -> AsyncIterator[dict[str, Any]]:
    memory_context = build_memory_prompt_context(user_id)
    if answer_assessment is None:
        async for event in _yield_orchestrator_assessment_events(
            user_message,
            results,
            user_id=user_id,
        ):
            if event.get("type") == _ORCH_ASSESSMENT_RESULT:
                answer_assessment = event["assessment"]
                continue
            yield event

    synth_id = f"agent-synth-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "汇总最终回答",
            "detail": "合并各子任务结果",
            "tool": "supervisor.synthesize",
            "step_id": synth_id,
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }
    screenshot_attachments = collect_screenshot_attachments_from_task_results(results)
    fast_reply = _try_orchestrator_final_reply_fast_path(
        user_message,
        results,
        answer_assessment=answer_assessment,
        screenshot_attachments=screenshot_attachments,
    )

    reply_parts: list[str] = []
    if fast_reply is not None:
        for chunk in _chunk_stream_deltas(fast_reply):
            reply_parts.append(chunk["text"])
            yield chunk
    else:
        async for ev in _iter_orchestrator_synthesis_events(
            user_message,
            results,
            memory_context=memory_context,
            screenshot_attachments=screenshot_attachments,
            answer_assessment=answer_assessment,
            step_id=synth_id,
        ):
            if ev.get("type") == "workflow":
                data = dict(ev.get("data") or {})
                data.setdefault("agent_id", "orchestrator")
                data.setdefault("agent_title", "小析调度")
                yield {"type": "workflow", "data": data}
            elif ev.get("type") == "delta" and ev.get("text"):
                reply_parts.append(str(ev["text"]))
                yield {"type": "delta", "text": ev["text"]}
            elif ev.get("type") == "complete_text":
                text = str(ev.get("text") or "").strip()
                for chunk in _chunk_stream_deltas(text):
                    reply_parts.append(chunk["text"])
                    yield chunk

    final_reply = append_screenshot_markdown_to_reply(
        "".join(reply_parts).strip(),
        screenshot_attachments if fast_reply is None else [],
    )
    for att in screenshot_attachments:
        yield {"type": "attachment", "data": att}
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "汇总完成",
            "detail": "",
            "tool": "supervisor.synthesize",
            "step_id": synth_id,
            "status": "done",
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }
    yield _build_final_complete(
        messages=messages,
        hop_completes=hop_completes,
        reply=final_reply or None,
    )


def _merge_context_instruction(base: str, extra: str) -> str:
    parts = [(base or "").strip(), (extra or "").strip()]
    return "\n\n".join(p for p in parts if p)


def _is_capability_gap_plan(plan: AgentRoutePlan) -> bool:
    return plan.source == "capability_gap"


def _is_auto_skill_dev_plan(plan: AgentRoutePlan) -> bool:
    return plan.source == "capability_gap_skill_dev"


async def _execute_route_plan(
    plan: AgentRoutePlan,
    *,
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    messages: list[dict[str, Any]],
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    defer_synthesis: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    routes = list(plan.routes)
    hop_context = _merge_context_instruction(
        context_instruction, plan.capability_gap_instruction
    )
    if not routes:
        if defer_synthesis:
            yield _round_result_event(results=[], hop_completes=[], messages=messages)
            return
        yield _build_final_complete(messages=messages, hop_completes=[], reply=None)
        return

    if len(routes) > 1:
        async for event in _execute_orchestrated_tasks(
            routes,
            sess=sess,
            user_id=user_id,
            messages=messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            retrieval_context=retrieval_context,
            context_instruction=hop_context,
            mode=plan.mode if plan.mode in ("sequential", "parallel") else "sequential",
            skip_plan_ui=False,
            defer_synthesis=defer_synthesis,
        ):
            yield event
        return

    if _is_capability_gap_plan(plan):
        from app.services.llm_workflow_stream import iter_llm_answer_events

        if plan.missing_capability_receipt:
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "平台能力范围说明",
                    "detail": str(plan.missing_capability_receipt.get("msg") or "")[:240],
                    "tool": "supervisor.capability_gap",
                    "step_id": f"cap-gap-{uuid.uuid4().hex[:8]}",
                    "status": "done",
                    "agent_id": "orchestrator",
                    "agent_title": "小析调度",
                    "receipt": plan.missing_capability_receipt,
                },
            }
        working = list(messages)
        if hop_context:
            working = [
                *working,
                {"role": "user", "content": hop_context},
            ]
        reply_parts: list[str] = []
        loop_id = f"cap-gap-{uuid.uuid4().hex[:8]}"
        async for ev in iter_llm_answer_events(
            messages=working,
            temperature=0.3,
            think_title="说明平台能力范围",
            think_detail="无匹配 Skill，仅文本反馈",
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
        complete = {
            "type": "complete",
            "messages": working,
            "reply": final_reply,
            "citations": [],
            "kg_context": None,
        }
        if defer_synthesis:
            result = _build_task_result_from_hop(
                routes[0], events=[], complete=complete
            )
            yield _round_result_event(
                results=[result],
                hop_completes=[complete],
                messages=working,
            )
        else:
            yield complete
        return

    if len(routes) == 1:
        if _is_auto_skill_dev_plan(plan):
            if defer_synthesis:
                async for event in _execute_auto_skill_dev_task(
                    sess=sess,
                    user_id=user_id,
                    route=routes[0],
                    user_message=user_message,
                    chat_history=chat_history,
                    retrieval_context=retrieval_context,
                    context_instruction=hop_context,
                    conversation_id=conversation_id,
                    attachment_session_id=attachment_session_id,
                    tools=tools,
                    intent_plan=intent_plan,
                    max_rounds=max_rounds,
                    messages=messages,
                ):
                    yield event
                return
            async for event in _execute_auto_skill_dev_task_interactive(
                sess=sess,
                user_id=user_id,
                route=routes[0],
                user_message=user_message,
                chat_history=chat_history,
                retrieval_context=retrieval_context,
                context_instruction=hop_context,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
            ):
                yield event
            return

        if defer_synthesis:
            hop_events = []
            complete = None
            agent_title = resolve_agent_title(routes[0].agent_id)
            async for event in _execute_tasks_with_orchestrator_progress(
                _run_specialist_hop(
                    sess,
                    user_id,
                    route=routes[0],
                    user_message=user_message,
                    chat_history=chat_history,
                    retrieval_context=retrieval_context,
                    context_instruction=context_instruction,
                    conversation_id=conversation_id,
                    attachment_session_id=attachment_session_id,
                    tools=tools,
                    intent_plan=intent_plan,
                    max_rounds=max_rounds,
                    task_mode=False,
                ),
                agent_titles=[agent_title],
            ):
                if event.get("type") == "complete":
                    complete = event
                    continue
                hop_events.append(event)
                if not _skip_hop_client_preview(event):
                    yield event
            result = _build_task_result_from_hop(
                routes[0], events=hop_events, complete=complete
            )
            yield _round_result_event(
                results=[result],
                hop_completes=[complete],
                messages=(complete or {}).get("messages") or messages,
            )
            return

        agent_title = resolve_agent_title(routes[0].agent_id)
        async for event in _execute_tasks_with_orchestrator_progress(
            _run_specialist_hop(
                sess,
                user_id,
                route=routes[0],
                user_message=user_message,
                chat_history=chat_history,
                retrieval_context=retrieval_context,
                context_instruction=context_instruction,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                task_mode=False,
            ),
            agent_titles=[agent_title],
        ):
            yield event
        return


async def iter_supervised_agent_loop(
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
    retrieval_context: str = "",
    context_instruction: str = "",
    skip_route_plan_ui: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Supervisor 入口：路由规划 → 子任务编排 → 全局验收 Loop → 终稿汇总。"""
    user_id = coerce_user_id(user)
    max_global_rounds = _supervisor_max_global_rounds()
    prior_outcomes: list[str] = []
    effective_context_instruction = context_instruction
    sess = AgentLoopSession(user_id)

    # 标记调度智能体（小析）为运行中
    conv_key = str(conversation_id or "")
    if conv_key:
        mark_agent_running("orchestrator", conv_key)

    try:
        for global_round in range(max_global_rounds):
            is_retry = global_round > 0
            # 立即发射调度事件，让前端第一时间显示状态
            if not is_retry and skip_route_plan_ui:
                yield _orchestrator_progress_event(
                    detail="小析调度：正在分析任务并分配智能体",
                )
            elif is_retry:
                retry_detail = prior_outcomes[-1][:240] if prior_outcomes else ""
                yield _global_loop_iteration_workflow(
                    global_round, max_global_rounds, retry_detail
                )

            route_plan_step_id = f"route-plan-{uuid.uuid4().hex[:8]}"
            show_plan_ui = (not skip_route_plan_ui) or is_retry
            if show_plan_ui:
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "agent_thinking",
                        "title": "正在规划方案" if not is_retry else "重新规划方案",
                        "detail": "",
                        "tool": "supervisor.plan",
                        "step_id": route_plan_step_id,
                        "agent_id": "orchestrator",
                        "agent_title": "小析调度",
                    },
                }

            db, bound_user = sess.open()
            try:
                plan = await resolve_agent_route_plan(
                    db,
                    bound_user,
                    user_message,
                    intent_plan=intent_plan,
                    chat_history=chat_history,
                    prior_outcomes=prior_outcomes if is_retry else None,
                    force_replan=is_retry,
                )
            finally:
                sess.release_before_io()

            route_titles = []
            route_details: list[str] = []
            for route in plan.routes:
                profile = get_agent_profile(route.agent_id)
                title = profile.title if profile else route.agent_id
                route_titles.append(title)
                if route.reason:
                    route_details.append(f"{title}：{route.reason}")
            if len(route_titles) == 1:
                plan_title = f"规划方案：{route_titles[0]}"
            elif route_titles:
                plan_title = f"规划方案：{' → '.join(route_titles)}"
            else:
                plan_title = "规划方案：调度智能体"
            plan_detail = (
                "\n".join(route_details[:4]) if route_details else "、".join(route_titles[:4])
            )
            if show_plan_ui:
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "agent_thought",
                        "title": plan_title,
                        "detail": plan_detail,
                        "tool": "supervisor.plan",
                        "step_id": route_plan_step_id,
                        "status": "done",
                        "agent_id": "orchestrator",
                        "agent_title": "小析调度",
                    },
                }

            defer_synthesis = _should_defer_orchestrator_synthesis(
                plan,
                user_message=user_message,
                chat_history=chat_history,
                max_global_rounds=max_global_rounds,
            )

            effective_user_message = user_message
            if plan.source == "capability_partial" and plan.feasible_goal.strip():
                effective_user_message = plan.feasible_goal.strip()
            round_context_instruction = _merge_context_instruction(
                effective_context_instruction,
                plan.capability_gap_instruction,
            )

            round_payload: dict[str, Any] | None = None
            async for event in _execute_route_plan(
                plan,
                sess=sess,
                user_id=user_id,
                messages=messages,
                conversation_id=conversation_id,
                max_rounds=max_rounds,
                user_message=effective_user_message,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                chat_history=chat_history,
                retrieval_context=retrieval_context,
                context_instruction=round_context_instruction,
                defer_synthesis=defer_synthesis,
            ):
                if event.get("type") == _ORCH_ROUND_RESULT:
                    round_payload = event
                    continue
                yield event

            if not defer_synthesis:
                return

            if round_payload is None:
                return

            results = list(round_payload.get("results") or [])
            hop_completes = list(round_payload.get("hop_completes") or [])
            round_messages = list(round_payload.get("messages") or messages)

            assessment: OrchestratorAnswerAssessment | None = None
            async for event in _yield_orchestrator_assessment_events(
                user_message,
                results,
                user_id=user_id,
            ):
                if event.get("type") == _ORCH_ASSESSMENT_RESULT:
                    assessment = event["assessment"]
                    continue
                yield event

            if assessment is None:
                return

            is_last_round = global_round >= max_global_rounds - 1
            if assessment.addresses_user or is_last_round:
                if is_last_round and not assessment.addresses_user:
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "agent_thought",
                            "title": "已达全局最大轮次",
                            "detail": (
                                assessment.gap or assessment.reason or "验收仍未通过"
                            )[:240],
                            "tool": "supervisor.global_loop",
                            "step_id": f"supervisor-global-cap-{uuid.uuid4().hex[:8]}",
                            "status": "failed",
                            "agent_id": "orchestrator",
                            "agent_title": "小析调度",
                        },
                    }
                async for event in _yield_orchestrator_synthesis(
                    user_message,
                    results,
                    user_id=user_id,
                    messages=round_messages,
                    hop_completes=hop_completes,
                    answer_assessment=assessment,
                ):
                    yield event
                return

            reflection = build_global_round_reflection(
                global_round=global_round,
                assessment=assessment,
                results=results,
            )
            if plan.missing_skill_tags:
                reflection = (
                    f"{reflection}\n缺失能力：{'、'.join(plan.missing_skill_tags)}"
                ).strip()
            append_supervisor_global_reflection(user_id, reflection)
            prior_outcomes.append(reflection[:800])
            effective_context_instruction = _build_global_retry_context_instruction(
                context_instruction,
                reflection,
                global_round=global_round + 1,
            )
    finally:
        if conv_key:
            mark_agent_idle("orchestrator", conv_key)
        sess.close()
