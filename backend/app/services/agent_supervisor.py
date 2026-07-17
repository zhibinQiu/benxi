"""多智能体 Supervisor — 意图路由、子智能体上下文与 handoff。"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any


from app.agentkit.aip.orchestration import merge_hop_citations
from app.core.agent.types import (
    AgentRoute,
    AgentRoutePlan,
)
from app.core.agent_loop_session import AgentLoopSession, coerce_user_id
from app.core.agent_profiles import get_agent_profile, resolve_agent_title

_ORCH_TITLE = resolve_agent_title("orchestrator")
from app.services.agent_aip_executor import (
    SpecialistExecutionContext,
    iter_builtin_specialist_hop,
)
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    AgentToolPlan,
)
from app.services.agent_orchestrator import (
    OrchestratorTask,
)
from app.config import get_settings
from app.services.agent_route_resolver import (
    resolve_agent_route_plan,
)
from app.services.agent_runtime_service import mark_agent_idle, mark_agent_running

_logger = logging.getLogger(__name__)

_HOP_CLIENT_PREVIEW_TYPES = frozenset({"replace", "delta"})


def _skip_hop_client_preview(event: dict[str, Any]) -> bool:
    """多智能体 hop 的中间回答仅用于 handoff，不下发前端（避免覆盖与二次闪烁）。"""
    return event.get("type") in _HOP_CLIENT_PREVIEW_TYPES


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
    agent_title: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    """调度端进度事件——表示调度正在工作中而非等待子任务完成。"""
    return {
        "type": "workflow",
        "data": {
            "phase": "orchestrator_progress",
            "title": "调度执行中",
            "detail": detail,
            "callDetail": f"{agent_title} 正在工作" if agent_title else detail,
            "tool": "supervisor.progress",
            "step_id": step_id or f"orch-progress-{uuid.uuid4().hex[:8]}",
            "agent_id": agent_id or "orchestrator",
            "agent_title": agent_title or _ORCH_TITLE,
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
        try:
            async for event in subagent_generator:
                # 检测 complete 事件 → 任务完成计数+1
                if event.get("type") == "complete":
                    completed = min(completed + 1, total)
                await queue.put(("event", event))
        except asyncio.TimeoutError:
            await queue.put(("timeout", None))
        except Exception as exc:
            import traceback
            await queue.put(("error", f"子任务异常：{exc}\n{traceback.format_exc()}"))
        finally:
            await queue.put(("_done", None))

    forward_task = asyncio.create_task(_subagent_forwarder())

    async def _progress_emitter():
        while True:
            await asyncio.sleep(progress_interval)
            running = agent_titles[completed:]
            if not running:
                # 全部完成，发射最终进度
                try:
                    await queue.put(
                        ("progress", _orchestrator_progress_event(detail=f"✔ 全部完成（{completed}/{total}）"))
                    )
                except asyncio.QueueFull:
                    pass
                continue
            try:
                detail = f"调度中 · {'、'.join(running)} · {completed}/{total}"
                running_agent = running[0] if running else ""
                await queue.put(("progress", _orchestrator_progress_event(
                    detail=detail,
                    agent_title=running_agent,
                )))
            except asyncio.QueueFull:
                pass

    progress_task = asyncio.create_task(_progress_emitter())

    timeout = getattr(get_settings(), "agent_subagent_timeout_sec", 600) or 600
    last_real_event_time = time.monotonic()
    max_stalled_sec = 45  # 连续 45 秒仅收到心跳事件（无 delta/workflow/complete），判定为卡住

    try:
        while True:
            stall_elapsed = time.monotonic() - last_real_event_time
            if stall_elapsed >= max_stalled_sec:
                _logger.warning(
                    "子任务 %s 秒未产出有效事件，强制结束。已完成 %d/%d",
                    max_stalled_sec, completed, total,
                )
                break
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                _logger.warning(
                    "子任务执行超时（%ss），强制结束。已完成 %d/%d",
                    timeout, completed, total,
                )
                break
            if kind == "_done":
                completed = total
                break
            elif kind == "timeout":
                _logger.warning("子任务生成器超时")
                break
            elif kind == "error":
                _logger.error("子任务异常：%s", payload[:500])
                yield {"type": "complete", "reply": f"子任务执行错误：{payload[:200]}", "messages": [], "citations": [], "kg_context": None}
                break
            elif kind == "event":
                last_real_event_time = time.monotonic()
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
) -> AsyncIterator[dict[str, Any]]:
    routes = list(plan.routes)
    hop_context = _merge_context_instruction(
        context_instruction, plan.capability_gap_instruction
    )
    if not routes:
        async for event in _execute_empty_routes(
            messages
        ):
            yield event
        return

    if _is_capability_gap_plan(plan):
        async for event in _execute_capability_gap(
            plan, routes[0], messages, hop_context
        ):
            yield event
        return

    async for event in _execute_single_route(
        routes[0], sess, user_id, messages, conversation_id,
        max_rounds, user_message, attachment_session_id,
        tools, intent_plan, chat_history, retrieval_context,
        context_instruction, hop_context, plan,
    ):
        yield event


async def _execute_empty_routes(
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    yield _build_final_complete(messages=messages, hop_completes=[], reply=None)


async def _execute_capability_gap(
    plan: AgentRoutePlan,
    route: AgentRoute,
    messages: list[dict[str, Any]],
    hop_context: str,
) -> AsyncIterator[dict[str, Any]]:
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
                "agent_title": _ORCH_TITLE,
                "receipt": plan.missing_capability_receipt,
            },
        }

    working = list(messages)
    if hop_context:
        working = [*working, {"role": "user", "content": hop_context}]
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
    yield complete


def _single_route_hop_kwargs(
    route: AgentRoute,
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
) -> dict[str, Any]:
    return dict(
        sess=sess,
        user_id=user_id,
        route=route,
        user_message=user_message,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
    )


async def _execute_single_route(
    route: AgentRoute,
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
    hop_context: str,
    plan: AgentRoutePlan,
) -> AsyncIterator[dict[str, Any]]:
    if _is_auto_skill_dev_plan(plan):
        kwargs = _single_route_hop_kwargs(
            route, sess, user_id, messages, conversation_id,
            max_rounds, user_message, attachment_session_id,
            tools, intent_plan, chat_history, retrieval_context, context_instruction,
        )
        async for event in _execute_auto_skill_dev_task_interactive(**kwargs):
            yield event
        return

    agent_title = resolve_agent_title(route.agent_id)
    hop_gen = _run_specialist_hop(
        sess,
        user_id,
        route=route,
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
    )

    needs_reroute = False
    assist_reason = ""
    got_complete = False
    async for event in _execute_tasks_with_orchestrator_progress(
        hop_gen, agent_titles=[agent_title]
    ):
        if event.get("type") == "complete":
            got_complete = True
            handoff_msg = event.get("aip_handoff")
            if handoff_msg and isinstance(handoff_msg, dict):
                payload = handoff_msg.get("payload", {})
                if isinstance(payload, dict) and payload.get("status") == "needs_assist":
                    needs_reroute = True
                    assist = payload.get("assist", {})
                    if isinstance(assist, dict):
                        assist_reason = str(assist.get("reason", "") or "")
                    if not assist_reason:
                        assist_reason = str(event.get("reply", "") or "")
                    continue  # 不转发 specialist 的 complete
            if not needs_reroute:
                yield event  # 正常完成，立即转发
        else:
            yield event  # 渐进式转发（workflow、delta 等）

    # 正常完成（complete 事件已在循环中 yield）→ 直接返回
    if got_complete and not needs_reroute:
        return

    # 安全兜底：如果 progress wrapper 未产出任何 complete（如异常吞没后退出），
    # 生成一个 fallback complete 事件，避免上游收不到循环结束信号
    if not got_complete and not needs_reroute:
        yield {
            "type": "complete",
            "reply": f"{agent_title} 执行未返回结果",
            "messages": [],
            "citations": [],
            "kg_context": None,
        }
        return

    # ── 专精智能体无法完成 → 重路由至调度智能体 ──
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": f"{agent_title} 请求调度协助",
            "detail": assist_reason[:120],
            "tool": "supervisor.reroute",
            "step_id": f"reroute-{uuid.uuid4().hex[:8]}",
            "status": "done",
            "agent_id": route.agent_id,
            "agent_title": agent_title,
        },
    }

    reroute_instruction = (
        f"【专精智能体无法完成，已交还调度】\n"
        f"用户原问题：{user_message}\n"
        f"专精智能体 [{agent_title}] 反馈：{assist_reason}\n\n"
        f"请根据以上信息重新处理用户请求，可直接回复或分配给其他智能体。"
    )

    orch_route = AgentRoute(
        agent_id="orchestrator",
        reason=f"{agent_title} 无法完成，由调度重新处理",
    )
    async for event in _run_specialist_hop(
        sess, user_id, route=orch_route,
        user_message=user_message,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=reroute_instruction,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=False,
    ):
        yield event


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
    """Supervisor 入口：路由规划 → 子任务执行，专精智能体的答复直接流式给用户。

    设计原则：
    - 调度智能体只负责理解用户意图和分配路由
    - 每个专精智能体的 tool loop（max_rounds）自行处理重试和完成判断
    - 专精智能体执行完成后，其最终回复直接流式给用户，调度不做验收/润色
    """
    user_id = coerce_user_id(user)
    sess = AgentLoopSession(user_id)

    # 标记调度智能体（小析）为运行中
    conv_key = str(conversation_id or "")
    if conv_key:
        mark_agent_running("orchestrator", conv_key)

    try:
        # ── 单次规划 ──
        if skip_route_plan_ui:
            yield _orchestrator_progress_event(
                detail=f"{_ORCH_TITLE}：正在分析任务并分配智能体",
            )

        route_plan_step_id = f"route-plan-{uuid.uuid4().hex[:8]}"
        if not skip_route_plan_ui:
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": "正在规划方案",
                    "detail": "",
                    "tool": "supervisor.plan",
                    "step_id": route_plan_step_id,
                    "agent_id": "orchestrator",
                    "agent_title": _ORCH_TITLE,
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
                prior_outcomes=None,
                force_replan=False,
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
        # 规划结果事件——始终发射，让前端能更新"正在分析"提示
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
                "agent_title": _ORCH_TITLE,
            },
        }

        round_context_instruction = _merge_context_instruction(
            context_instruction,
            plan.capability_gap_instruction,
        )

        effective_user_message = user_message
        if plan.source == "capability_partial" and plan.feasible_goal.strip():
            effective_user_message = plan.feasible_goal.strip()

        # ── 专精智能体执行，其答复直接流式给用户 ──
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
        ):
            yield event
    finally:
        if conv_key:
            mark_agent_idle("orchestrator", conv_key)
        sess.close()
