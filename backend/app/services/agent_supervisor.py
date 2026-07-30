"""多智能体 Supervisor — 意图路由、子智能体上下文与 handoff。"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agent.aip.orchestration import merge_hop_citations
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
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    task_mode: bool = False,
    round_state: dict | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """执行单次专精 hop（委托 AIP 执行层）。"""
    ctx = SpecialistExecutionContext(
        agent_id=route.agent_id,
        user_message=user_message,
        session_id=(conversation_id or "").strip() or f"session-{uuid.uuid4().hex[:8]}",
        task_id=f"task-{uuid.uuid4().hex[:8]}",
        reason=route.reason,
        chat_history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        attachment_session_id=attachment_session_id,
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=task_mode,
    )
    conv_key = ctx.session_id
    mark_agent_running(route.agent_id, conv_key)
    try:
        async for event in iter_builtin_specialist_hop(sess, user_id, ctx, round_state=round_state):
            yield event
    except Exception:
        _logger.exception("Specialist hop 异常中断 agent=%s", route.agent_id)
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "执行中断",
                "detail": "智能体执行时遇到错误，请联系管理员或稍后重试",
                "tool": "supervisor.route",
                "status": "error",
            },
        }
        yield {
            "type": "complete",
            "messages": [
                {"role": "assistant", "content": "抱歉，智能体执行时遇到错误，请稍后重试。"}
            ],
            "reply": "抱歉，智能体执行时遇到错误，请稍后重试。",
            "citations": [],
            "kg_context": None,
        }
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
    tools: list[dict[str, Any]] | None = None,
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
        intent_plan=intent_plan,
        max_rounds=max_rounds,
        task_mode=True,
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


def _merge_context_instruction(base: str, extra: str) -> str:
    parts = [(base or "").strip(), (extra or "").strip()]
    return "\n\n".join(p for p in parts if p)


def _is_capability_gap_plan(plan: AgentRoutePlan) -> bool:
    return plan.source == "capability_gap"


def _is_auto_skill_dev_plan(plan: AgentRoutePlan) -> bool:
    return plan.source == "capability_gap_skill_dev"


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


async def _execute_task_dag(
    sess: AgentLoopSession,
    user_id: uuid.UUID,
    *,
    dag,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    retrieval_context: str,
    context_instruction: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    intent_plan: AgentToolPlan | None,
    max_rounds: int | None,
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """按 TaskDAG 波次调度专精 hop，综合终稿。"""
    from app.agent.orchestrate.scheduler import iter_dag_wave_events
    from app.agent.orchestrate.types import ORCH_TASK_RESULT, TaskExecutionResult
    from app.config import get_settings
    from app.core.stream_cancel import raise_if_stream_cancelled
    from app.services.agent_orchestrator import workflow_plan_tasks
    from app.services.agent_task_dag_planner import (
        agent_plan_detail_lines,
        build_node_user_message,
        synthesize_dag_final_reply,
    )

    step_id = f"dag-{uuid.uuid4().hex[:8]}"
    yield workflow_plan_tasks(
        dag.orchestrator_tasks(),
        step_id=step_id,
        mode="dag",
        detail=dag.summary_chain(),
        edges=dag.edges(),
    )
    plan_detail = agent_plan_detail_lines(dag)
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_plan",
            "title": "制定计划",
            "detail": plan_detail,
            "tool": "supervisor.plan",
            "step_id": step_id,
            "mode": "dag",
            "agent_id": "orchestrator",
            "agent_title": _ORCH_TITLE,
        },
    }

    hop_completes: list[dict[str, Any]] = []
    cfg = get_settings()
    max_par = max(1, int(getattr(cfg, "agent_max_parallel_handoffs", 3) or 3))

    async def run_one_node(*, node, task, route, **_kw):
        parent_replies = dag.parent_replies(node.id)
        node_msg = build_node_user_message(user_message, node, parent_replies)
        complete = None
        events: list[dict[str, Any]] = []
        async for event in _run_specialist_hop(
            sess,
            user_id,
            route=route,
            user_message=node_msg,
            chat_history=chat_history,
            retrieval_context=retrieval_context,
            context_instruction=context_instruction,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            intent_plan=intent_plan,
            max_rounds=max_rounds,
            task_mode=True,
        ):
            if event.get("type") == "complete":
                complete = event
            elif event.get("type") == "step_complete":
                complete = {
                    "type": "complete",
                    "reply": event.get("reply"),
                    "messages": event.get("working") or [],
                    "citations": list(
                        (event.get("loop_state") or {}).get("citations") or []
                    ),
                    "kg_context": (event.get("loop_state") or {}).get("kg_context"),
                }
            elif not _skip_hop_client_preview(event):
                events.append(event)
                yield event
        result = TaskExecutionResult(
            task=task,
            route=route,
            events=events,
            complete=complete,
            satisfied=bool(str((complete or {}).get("reply") or "").strip()),
        )
        yield {"type": ORCH_TASK_RESULT, "result": result}

    async for kind, payload in iter_dag_wave_events(
        dag,
        run_one_node=run_one_node,
        max_parallel=max_par,
        agent_title_fn=resolve_agent_title,
    ):
        raise_if_stream_cancelled()
        if kind == "event":
            yield payload
        elif kind == "result" and isinstance(payload, TaskExecutionResult):
            if payload.complete:
                hop_completes.append(payload.complete)

    results = dag.done_results()
    reply = await synthesize_dag_final_reply(user_message, results)
    if not reply:
        # 全部失败时仍给出可读说明
        failed = [n for n in dag.nodes if n.status == "failed"]
        if failed:
            reply = "部分子任务未能完成：" + "；".join(
                f"{n.title}（{n.last_error or '无结果'}）" for n in failed[:4]
            )
    yield _build_final_complete(
        messages=messages, hop_completes=hop_completes, reply=reply or None
    )


async def iter_supervised_agent_loop(
    user: User | uuid.UUID,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None = None,
    max_rounds: int | None = None,
    user_message: str = "",
    attachment_session_id: str | None = None,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
    retrieval_context: str = "",
    context_instruction: str = "",
    skip_route_plan_ui: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Supervisor 入口：路由规划 → 执行。

    设计原则：
    - 调度智能体只负责理解用户意图和分配路由
    - 每个专精智能体的 tool loop 自行处理重试和完成判断
    - 保持最简单的 yield 链，不使用队列/后台任务包装
    """
    user_id = coerce_user_id(user)
    sess = AgentLoopSession(user_id)
    conv_key = str(conversation_id or "")
    if conv_key:
        mark_agent_running("orchestrator", conv_key)

    try:
        _t_start = time.monotonic()

        # ── 路由规划 ──
        if skip_route_plan_ui:
            yield _orchestrator_progress_event(
                detail=f"{_ORCH_TITLE}：正在分析任务并分配智能体",
            )

        route_plan_step_id = f"route-plan-{uuid.uuid4().hex[:8]}"
        will_semantic_probe = False
        if not skip_route_plan_ui:
            # 硬规则可瞬间返回；需图谱探测时再显示本体/图谱服务步骤
            from app.services.agent_route_resolver import _resolve_hard_rule_routes
            from app.services.agent_skill_router import should_skip_kg_probe
            from app.services.semantic_workflow import semantic_probe_start_events

            db_pre, bound_pre = sess.open()
            try:
                hard_pre = _resolve_hard_rule_routes(db_pre, user_message)
            finally:
                sess.release_before_io()
            if hard_pre is not None:
                thinking_title = "正在规划方案"
            elif should_skip_kg_probe(user_message):
                thinking_title = "正在规划方案"
            else:
                will_semantic_probe = True
                thinking_title = "本体语义中枢与知识图谱服务"
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": thinking_title,
                    "detail": (
                        "先理解概念并规划路径，再检索图谱事实"
                        if will_semantic_probe
                        else ""
                    ),
                    "tool": "supervisor.plan",
                    "step_id": route_plan_step_id,
                    "agent_id": "orchestrator",
                    "agent_title": _ORCH_TITLE,
                },
            }
            if will_semantic_probe:
                for ev in semantic_probe_start_events(
                    route_plan_step_id,
                    agent_id="orchestrator",
                    agent_title=_ORCH_TITLE,
                ):
                    yield {"type": "workflow", "data": ev}

        _logger.info("SUPERVISOR: pre-route-plan %.1fs msg=%s",
                     time.monotonic() - _t_start, user_message[:60])
        db, bound_user = sess.open()
        try:
            plan = await resolve_agent_route_plan(
                db, bound_user, user_message,
                chat_history=chat_history,
                prior_outcomes=None, force_replan=False,
            )
        finally:
            sess.release_before_io()

        from app.core.stream_cancel import raise_if_stream_cancelled

        raise_if_stream_cancelled()

        # 知识图谱已足以作答：跳过 Skill/Agent 匹配与 tool loop，立刻推送正文
        kg_direct = (plan.direct_reply or "").strip() if plan.source == "kg_direct" else ""
        kg_ctx = (plan.kg_context_text or "").strip()
        if will_semantic_probe and not skip_route_plan_ui:
            from app.services.semantic_workflow import semantic_probe_done_events

            for ev in semantic_probe_done_events(
                route_plan_step_id,
                planning_text=kg_ctx,
                direct=bool(kg_direct),
                has_material=bool(kg_ctx),
                agent_id="orchestrator",
                agent_title=_ORCH_TITLE,
            ):
                yield {"type": "workflow", "data": ev}
        if kg_direct:
            yield {"type": "replace", "text": kg_direct}
            yield {
                "type": "complete",
                "messages": list(messages or []),
                "reply": kg_direct,
                "citations": [],
                "kg_context": None,
            }
            return

        # 本轮图谱探测结果并入检索上下文，避免 tool loop 重复推理
        effective_retrieval = retrieval_context or ""
        if kg_ctx and kg_ctx not in effective_retrieval:
            from app.services.agent_planner import _KG_PLANNING_USER_LABEL

            block = f"{_KG_PLANNING_USER_LABEL}\n{kg_ctx}"
            effective_retrieval = (
                f"{effective_retrieval.rstrip()}\n\n{block}".strip()
                if effective_retrieval.strip()
                else block
            )

        route_titles: list[str] = []
        route_details: list[str] = []
        for route in plan.routes:
            profile = get_agent_profile(route.agent_id)
            title = profile.title if profile else route.agent_id
            route_titles.append(title)
            if route.reason:
                route_details.append(route.reason)
        plan_title = (
            f"规划方案：{route_titles[0]}"
            if len(route_titles) == 1
            else f"规划方案：{' → '.join(route_titles)}"
            if route_titles
            else "规划方案：小析"
        )
        plan_detail = (
            "；".join(route_details[:4]) if route_details
            else "、".join(route_titles[:4])
        )
        from app.services.agent_working_memory import WorkingMemory

        working_memory = WorkingMemory()
        first_route = plan.routes[0] if plan.routes else None
        if first_route:
            working_memory.observe_route(
                source=str(plan.source or ""),
                agent_id=first_route.agent_id,
                reason=plan_detail or first_route.reason or "",
            )
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": plan_title,
                "detail": plan_detail or "正在根据用户意图选择处理路径",
                "tool": "supervisor.plan",
                "step_id": route_plan_step_id,
                "status": "done",
                "agent_id": "orchestrator",
                "agent_title": _ORCH_TITLE,
            },
        }

        hop_context = _merge_context_instruction(
            context_instruction, plan.capability_gap_instruction,
        )
        hop_context = _merge_context_instruction(
            hop_context, working_memory.format_prompt_block(),
        )
        routes = list(plan.routes)

        # ── 无路由 → 直接返回 ──
        if not routes:
            yield _build_final_complete(
                messages=messages, hop_completes=[], reply=None)
            return

        # ── Task DAG：复合 / 多路由统一走波次调度 ──
        mode = (plan.mode or "single").strip().lower()
        if not _is_capability_gap_plan(plan) and not _is_auto_skill_dev_plan(plan):
            from app.services.agent_task_dag_planner import (
                dag_from_flat_routes,
                maybe_plan_task_dag,
            )

            db_dag, bound_dag = sess.open()
            try:
                task_dag = await maybe_plan_task_dag(
                    db_dag,
                    bound_dag,
                    user_message,
                    chat_history=chat_history,
                    route_plan=plan,
                )
            finally:
                sess.release_before_io()
            if task_dag is None and len(routes) > 1:
                task_dag = dag_from_flat_routes(
                    routes, message=user_message, mode=mode,
                )
            if task_dag is not None and len(task_dag.nodes) > 1:
                async for event in _execute_task_dag(
                    sess,
                    user_id,
                    dag=task_dag,
                    user_message=user_message,
                    chat_history=chat_history,
                    retrieval_context=effective_retrieval,
                    context_instruction=hop_context,
                    conversation_id=conversation_id,
                    attachment_session_id=attachment_session_id,
                    intent_plan=intent_plan,
                    max_rounds=max_rounds,
                    messages=messages,
                ):
                    yield event
                return

        route = routes[0]

        _logger.info("SUPERVISOR: post-route-plan %.1fs route=%s first_route=%s",
                     time.monotonic() - _t_start, plan.source, route.agent_id)

        # ── 能力缺口计划 ──
        if _is_capability_gap_plan(plan):
            async for event in _execute_capability_gap(
                plan, route, messages, hop_context,
            ):
                yield event
            return

        # ── 自动 Skill 创建 ──
        if _is_auto_skill_dev_plan(plan):
            async for event in _execute_auto_skill_dev_task_interactive(
                sess=sess, user_id=user_id, route=route,
                user_message=user_message, chat_history=chat_history,
                retrieval_context=effective_retrieval,
                context_instruction=hop_context,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                intent_plan=intent_plan, max_rounds=max_rounds,
            ):
                yield event
            return

        # ── 普通执行：Supervisor 循环调度子智能体 ──
        effective_user_message = user_message
        if plan.source == "capability_partial" and plan.feasible_goal.strip():
            effective_user_message = plan.feasible_goal.strip()

        agent_title = resolve_agent_title(route.agent_id)
        round_state: dict | None = None
        max_supervisor_rounds = max_rounds or 8
        needs_reroute = False
        assist_reason = ""
        hop_messages: list[dict] = []

        for _sv_round in range(max_supervisor_rounds):
            from app.core.stream_cancel import raise_if_stream_cancelled

            raise_if_stream_cancelled()
            working_memory.record(
                "执行轮次",
                f"第 {_sv_round + 1} 轮",
                agent_id=route.agent_id,
            )
            hop_context = _merge_context_instruction(
                _merge_context_instruction(
                    context_instruction, plan.capability_gap_instruction,
                ),
                working_memory.format_prompt_block(),
            )
            gen = _run_specialist_hop(
                sess, user_id,
                route=route,
                user_message=effective_user_message,
                chat_history=chat_history,
                retrieval_context=effective_retrieval,
                context_instruction=hop_context,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                task_mode=False,
                round_state=round_state,
            )
            step_result: dict | None = None
            got_complete = False
            needs_reroute = False
            assist_reason = ""

            async for event in gen:
                working_memory.observe_stream_event(event)
                if event.get("type") == "step_complete":
                    step_result = event
                    # step_complete 之后不再有其他事件，break 让外层处理
                    break
                elif event.get("type") == "complete":
                    # orchestrator 路径保持原有多轮 complete 处理
                    got_complete = True
                    hop_messages = list(event.get("messages") or [])
                    handoff_msg = event.get("aip_handoff")
                    if handoff_msg and isinstance(handoff_msg, dict):
                        pl = handoff_msg.get("payload", {})
                        if isinstance(pl, dict) and pl.get("status") == "needs_assist":
                            needs_reroute = True
                            assist = pl.get("assist", {})
                            if isinstance(assist, dict):
                                assist_reason = str(assist.get("reason", "") or "")
                            if not assist_reason:
                                assist_reason = str(event.get("reply", "") or "")
                            continue
                    if not needs_reroute:
                        yield event
                        return
                else:
                    yield event

            # ── orchestrator 路径：保持原有多轮处理 ──
            if got_complete and not needs_reroute:
                return
            if got_complete and needs_reroute:
                # orchestrator 请求协助 → 重路由（同旧逻辑）
                break  # 跳出 for 循环，执行下方重路由

            # ── 专精智能体 step_complete 处理 ──
            if step_result is not None:
                round_state = step_result  # 保存给下一轮
                needs_more = step_result.get("needs_more_rounds", False)
                orch_assist = step_result.get("orchestrator_assist_request")

                if orch_assist:
                    # 子智能体通过 request_orchestrator_assist 请求调度协助
                    break  # 跳出 for 循环，执行下方重路由

                if needs_more:
                    continue  # 继续下一轮

                # 本步结束：有工具证据则由父层综合终稿，禁止透传子智能体正文/工具清单
                working = list(step_result.get("working") or [])
                loop_state = dict(step_result.get("loop_state") or {})
                from app.services.agent_reply_synth import has_deliverable_evidence
                from app.services.agent_tool_loop import emit_final_user_reply
                from app.agent.message.filter import has_mermaid_deliverable

                diagram_reply = str(
                    step_result.get("reply")
                    or loop_state.get("deterministic_reply")
                    or loop_state.get("task_deliverable")
                    or ""
                ).strip()
                if has_mermaid_deliverable(diagram_reply):
                    # 图表交付物原样下发，避免再综合丢失围栏
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "agent_thought",
                            "title": "执行完成",
                            "detail": "已生成流程图",
                            "tool": "supervisor.finish",
                            "status": "done",
                        },
                    }
                    yield {
                        "type": "complete",
                        "messages": working,
                        "reply": diagram_reply,
                        "citations": list(loop_state.get("citations") or []),
                        "kg_context": loop_state.get("kg_context"),
                    }
                    return

                if has_deliverable_evidence(loop_state):
                    async for ev in emit_final_user_reply(
                        sess,
                        user_id,
                        f"agent-tools-{uuid.uuid4().hex[:8]}",
                        effective_user_message,
                        working,
                        loop_state,
                        chat_history=chat_history,
                    ):
                        yield ev
                    return

                reply = str(step_result.get("reply") or "").strip()

                # 专精未交付 → 事实回执写入工作时记忆，交还调度重编排（禁止把编造答复当终稿）
                if route.agent_id != "orchestrator":
                    assist_reason = working_memory.add_failure_receipt(
                        agent_id=route.agent_id,
                        agent_title=agent_title,
                        loop_state=loop_state,
                        reply=reply,
                    )
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "agent_thought",
                            "title": f"{agent_title} 无法完成，交还调度",
                            "detail": assist_reason[:240],
                            "tool": "supervisor.reroute",
                            "status": "done",
                            "agent_id": route.agent_id,
                            "agent_title": agent_title,
                        },
                    }
                    needs_reroute = True
                    break

                if not reply:
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "agent_thought",
                            "title": "未能完成",
                            "detail": (
                                f"{agent_title} 本轮未产出可交付结果；"
                                "已尝试调用可用工具，但仍缺少有效证据。"
                            ),
                            "tool": "supervisor.finish",
                            "status": "failed",
                            "agent_id": route.agent_id,
                            "agent_title": agent_title,
                        },
                    }
                yield {
                    "type": "complete",
                    "reply": reply or "抱歉，这次没能完成您的请求。请补充更具体的要求后重试。",
                    "messages": working,
                    "citations": list(loop_state.get("citations") or []),
                    "kg_context": loop_state.get("kg_context"),
                }
                return

            # ── 安全兜底：无 step_complete 也无 complete ──
            if not needs_reroute:
                _logger.warning(
                    "专精智能体 %s 未产出 step_complete 事件，触发安全兜底",
                    agent_title,
                )
                yield {
                    "type": "complete",
                    "reply": f"{agent_title} 执行异常中断（未收到完成信号）",
                    "messages": [], "citations": [], "kg_context": None,
                }
                return

        # ── 超出最大轮次 or 请求协助 / 专精失败回交 ──
        if needs_reroute or round_state and round_state.get("orchestrator_assist_request"):
            # 构建重路由指令
            if not assist_reason and step_result:
                assist_reason = str(step_result.get("reply") or "")[:120]
            if round_state and round_state.get("orchestrator_assist_request"):
                working_memory.record(
                    "请求调度协助",
                    assist_reason or "需要调度协助",
                    agent_id=route.agent_id,
                )
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": f"{agent_title} 请求调度协助",
                    "detail": assist_reason or "需要调度协助",
                    "tool": "supervisor.reroute",
                    "step_id": f"reroute-{uuid.uuid4().hex[:8]}",
                    "status": "done",
                    "agent_id": route.agent_id,
                    "agent_title": agent_title,
                },
            }
            wm_block = working_memory.format_prompt_block()
            reroute_instruction = _merge_context_instruction(
                (
                    f"【专精智能体无法完成，已交还调度】\n"
                    f"用户原问题：{user_message}\n"
                    f"失败回执：{assist_reason or '需要协助'}\n\n"
                    f"约束：不得编造工具未返回的数据；须根据工作时记忆中的失败事实"
                    f"重新编排（改用合适工具/子智能体，或分配更合适的智能体）。"
                ),
                wm_block,
            )
            orch_route = AgentRoute(
                agent_id="orchestrator",
                reason=f"{agent_title} 无法完成，由调度重新处理",
            )
            async for event in _run_specialist_hop(
                sess, user_id,
                route=orch_route,
                user_message=user_message,
                chat_history=chat_history,
                retrieval_context=effective_retrieval,
                context_instruction=reroute_instruction,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
                task_mode=False,
            ):
                yield event
            return

        # ── 超出最大轮次：有证据则综合终稿，避免空报错丢弃已取到的结果 ──
        _logger.warning(
            "专精智能体 %s 达到最大 supervisor 轮次 %d 仍未完成",
            agent_title, max_supervisor_rounds,
        )
        if round_state is not None:
            working = list(round_state.get("working") or [])
            loop_state = dict(round_state.get("loop_state") or {})
            from app.services.agent_reply_synth import has_deliverable_evidence
            from app.services.agent_tool_loop import emit_final_user_reply

            if has_deliverable_evidence(loop_state):
                async for ev in emit_final_user_reply(
                    sess,
                    user_id,
                    f"agent-tools-{uuid.uuid4().hex[:8]}",
                    effective_user_message,
                    working,
                    loop_state,
                    chat_history=chat_history,
                ):
                    yield ev
                return
            reply = str(round_state.get("reply") or "").strip()
            if reply:
                yield {
                    "type": "complete",
                    "reply": reply,
                    "messages": working,
                    "citations": list(loop_state.get("citations") or []),
                    "kg_context": loop_state.get("kg_context"),
                }
                return
        yield {
            "type": "complete",
            "reply": f"{agent_title} 已达到最大执行轮次，请精简您的请求后重试。",
            "messages": [], "citations": [], "kg_context": None,
        }

    except Exception:
        _logger.exception("iter_supervised_agent_loop 异常中断 user=%s", user_id)
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "任务中断",
                "detail": "小析遇到错误，请稍后重试",
                "tool": "supervisor.error",
                "status": "error",
            },
        }
        yield {
            "type": "complete",
            "messages": messages,
            "reply": "抱歉，系统处理您的请求时遇到错误，请稍后重试。",
            "citations": [],
            "kg_context": None,
        }
    finally:
        if conv_key:
            mark_agent_idle("orchestrator", conv_key)
        sess.close()