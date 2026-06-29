"""多智能体 Supervisor — 意图路由、子智能体上下文与 handoff。"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_loop_session import AgentLoopSession, coerce_user_id
from app.core.agent_profiles import AGENT_PROFILES, get_agent_profile, resolve_agent_title
from app.core.llm_parse import parse_llm_json
from app.core.aip.messaging import reply_text_from_complete
from app.core.aip.session_bus import get_session_bus
from app.services.agent_aip_executor import (
    SpecialistExecutionContext,
    iter_builtin_specialist_hop,
    record_handoff_to_session,
)
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    AgentToolPlan,
    is_chitchat_message,
    needs_knowledge_retrieval,
    needs_web_search,
)
from app.core.platform_assistant import assistant_conclusion_source_priority, assistant_user_communication_style
from app.services.agent_memory_service import build_memory_prompt_context
from app.services.agent_orchestrator import (
    MAX_TASK_ATTEMPTS,
    OrchestratorTask,
    TaskExecutionResult,
    append_screenshot_markdown_to_reply,
    build_retry_user_message,
    collect_screenshot_attachments_from_task_results,
    new_plan_step_id,
    new_task_step_id,
    tasks_from_routes,
    verify_task_result,
    workflow_plan_tasks,
    workflow_task_event,
)
from app.services.agent_profile_service import (
    is_agent_enabled,
    resolve_agent_tool_names,
)
from app.services.agent_runtime_service import mark_agent_idle, mark_agent_running
from app.services.agent_routing_signals import (
    is_compound_parallel_message,
    is_compound_sequential_message,
    is_trivial_direct_question,
    matches_browser_intent,
    matches_browser_site_search,
    matches_platform_ops_extra,
    matches_research_signal,
    matches_scheduler_intent,
)
from app.services.agent_skill_router import (
    is_diagram_generation_message,
    is_platform_operation_message,
    is_skill_management_message,
    user_wants_browser_screenshot,
)
from app.services.agent_routing_catalog import (
    build_supervisor_routing_catalog,
    message_targets_uploaded_skill,
)
from app.services.report_agent_skills import is_report_generation_message
_logger = logging.getLogger(__name__)

RouteMode = Literal["single", "sequential", "parallel"]

_ROUTE_EXECUTION_ORDER = ("report", "research", "diagram", "platform", "scheduler", "rpa")
_HOP_CLIENT_PREVIEW_TYPES = frozenset({"replace", "delta"})
_ORCH_TASK_RESULT = "_orchestrator_task_result"


def _skip_hop_client_preview(event: dict[str, Any]) -> bool:
    """多智能体 hop 的中间回答仅用于 handoff，不下发前端（避免覆盖与二次闪烁）。"""
    return event.get("type") in _HOP_CLIENT_PREVIEW_TYPES


_ROUTE_REASONS: dict[str, str] = {
    "research": "资料检索 / 知识问答",
    "report": "结构化长报告撰写",
    "diagram": "思维导图 / 流程图 / Mermaid 图表",
    "platform": "平台文档 / 待办 / 系统数据",
    "scheduler": "定时任务 / 延迟提醒",
    "rpa": "浏览器 / 网页交互",
    "skill-dev": "Skill 创建/更新/执行",
    "orchestrator": "日常交流",
}
_LLM_ROUTE_AGENT_IDS = frozenset(
    {
        "orchestrator",
        "platform",
        "research",
        "report",
        "diagram",
        "rpa",
        "scheduler",
        "skill-dev",
    }
)
_SINGLE_ROUTE_PRIORITY = (
    "skill-dev",
    "platform",
    "scheduler",
    "rpa",
    "report",
    "diagram",
    "research",
)


@dataclass(frozen=True)
class AgentRoute:
    agent_id: str
    reason: str


@dataclass(frozen=True)
class AgentRoutePlan:
    mode: RouteMode
    routes: tuple[AgentRoute, ...]
    source: str = "rule"


def _pick_route(db: Session, agent_id: str, reason: str) -> AgentRoute:
    if is_agent_enabled(db, agent_id):
        return AgentRoute(agent_id=agent_id, reason=reason)
    return AgentRoute(
        agent_id="orchestrator",
        reason=f"{reason}（{agent_id} 已禁用，由调度智能体处理）",
    )


def _is_trivial_direct_question(msg: str) -> bool:
    return is_trivial_direct_question(msg)


def _is_direct_conversation_fast_path(
    message: str,
    route: AgentRoute,
    chat_history: list[AiChatMessage] | None,
) -> bool:
    """单路由 orchestrator 寒暄/简单问：跳过子任务编排与汇总 LLM。"""
    if route.agent_id != "orchestrator":
        return False
    msg = (message or "").strip()
    if not msg:
        return False
    if is_chitchat_message(msg, chat_history):
        return True
    return _is_trivial_direct_question(msg)


def _domain_flags(
    db: Session,
    user: User,
    msg: str,
    *,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
) -> dict[str, bool]:
    plan = intent_plan
    skill_dev = is_skill_management_message(msg)
    skill_exec = message_targets_uploaded_skill(db, user, msg, chat_history)
    if skill_exec:
        skill_dev = True
    rpa = matches_browser_intent(msg) and bool(resolve_agent_tool_names(db, "rpa"))
    scheduler = matches_scheduler_intent(msg)
    platform = is_platform_operation_message(msg) or matches_platform_ops_extra(msg)
    explicit_research = bool(
        matches_research_signal(msg)
        or (plan and plan.use_attachment)
        or (
            needs_knowledge_retrieval(msg, chat_history)
            and not is_platform_operation_message(msg)
            and not _is_trivial_direct_question(msg)
        )
    )
    diagram = is_diagram_generation_message(msg)
    report = is_report_generation_message(msg)
    # 撰写长报告走 report 专精；其自带检索工具，勿并行 research。
    if report:
        explicit_research = False
    # 纯图表诉求不走 research（避免「生成思维导图」误触发检索专精）。
    if diagram and not re.search(r"知识库|文档库|平台文档|检索|联网", msg, re.I):
        explicit_research = False
    # 路由到 research 须为明确检索意图；勿将「默认倾向联网」误判为专精路由。
    research = explicit_research
    if (
        platform
        and research
        and is_platform_operation_message(msg)
        and not matches_research_signal(msg)
    ):
        research = False
    # 浏览器站点搜索 / 截图类诉求走 RPA，勿并行 research（避免 web_search 代替百度截图）。
    if rpa and research and not re.search(r"知识库|文档库|平台文档", msg, re.I):
        if matches_browser_site_search(msg) or matches_browser_intent(msg):
            research = False
    if skill_exec:
        research = False
        orchestrator = False
    elif skill_dev and not is_chitchat_message(msg):
        orchestrator = False
    orchestrator = bool(is_chitchat_message(msg)) and not skill_dev
    return {
        "skill-dev": skill_dev,
        "rpa": rpa,
        "scheduler": scheduler,
        "platform": platform,
        "research": research,
        "report": report,
        "diagram": diagram,
        "orchestrator": orchestrator,
    }


def _pick_single_route_from_candidates(
    routes: list[AgentRoute],
    intent_plan: AgentToolPlan | None,
) -> AgentRoute:
    if not routes:
        raise ValueError("routes must not be empty")
    if len(routes) == 1:
        return routes[0]
    label = (intent_plan.intent_label if intent_plan else "") or ""
    if "平台" in label:
        for route in routes:
            if route.agent_id == "platform":
                return route
    if "日常" in label:
        for route in routes:
            if route.agent_id == "orchestrator":
                return route
    for agent_id in _SINGLE_ROUTE_PRIORITY:
        for route in routes:
            if route.agent_id == agent_id:
                return route
    return routes[0]


def _best_reply_from_hops(hop_completes: list[dict[str, Any] | None]) -> str | None:
    for event in reversed(hop_completes):
        text = reply_text_from_complete(event)
        if text:
            return text
    return None


def _resolve_agent_routes_rule(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> list[AgentRoute]:
    msg = (message or "").strip()
    flags = _domain_flags(
        db, user, msg, intent_plan=intent_plan, chat_history=chat_history
    )

    if flags["skill-dev"]:
        if (
            flags["rpa"]
            and not is_skill_management_message(msg)
            and (
                matches_browser_site_search(msg)
                or (
                    user_wants_browser_screenshot(msg)
                    and matches_browser_intent(msg)
                )
            )
        ):
            return [_pick_route(db, "rpa", _ROUTE_REASONS["rpa"])]
        return [_pick_route(db, "skill-dev", _ROUTE_REASONS["skill-dev"])]

    if flags["report"] and not any(
        flags[k] for k in ("platform", "scheduler", "rpa", "skill-dev")
    ):
        return [_pick_route(db, "report", _ROUTE_REASONS["report"])]

    if flags["diagram"] and not any(
        flags[k] for k in ("research", "platform", "scheduler", "rpa", "report")
    ):
        return [_pick_route(db, "diagram", _ROUTE_REASONS["diagram"])]

    others_active = any(flags[k] for k in _ROUTE_EXECUTION_ORDER)
    if flags["orchestrator"] and not others_active:
        return [_pick_route(db, "orchestrator", _ROUTE_REASONS["orchestrator"])]

    ordered_ids: list[str] = [
        agent_id for agent_id in _ROUTE_EXECUTION_ORDER if flags.get(agent_id)
    ]
    if not ordered_ids:
        if flags["orchestrator"]:
            return [_pick_route(db, "orchestrator", _ROUTE_REASONS["orchestrator"])]
        if message_targets_uploaded_skill(db, user, msg, chat_history):
            return [_pick_route(db, "skill-dev", _ROUTE_REASONS["skill-dev"])]
        if (
            needs_web_search(msg, chat_history)
            and not is_chitchat_message(msg)
            and not _is_trivial_direct_question(msg)
        ):
            return [_pick_route(db, "research", _ROUTE_REASONS["research"])]
        return [_pick_route(db, "orchestrator", "日常问答（默认调度智能体）")]

    return [
        _pick_route(db, agent_id, _ROUTE_REASONS.get(agent_id, agent_id))
        for agent_id in ordered_ids
    ]


def _infer_route_mode(message: str, route_count: int) -> RouteMode:
    if route_count <= 1:
        return "single"
    msg = (message or "").strip()
    if is_compound_sequential_message(msg):
        return "sequential"
    settings = get_settings()
    if (
        settings.agent_parallel_handoff_enabled
        and is_compound_parallel_message(msg)
    ):
        return "parallel"
    return "sequential"


def merge_hop_citations(citation_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """合并多智能体 hop 的引用，按出现顺序去重。"""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citations in citation_lists:
        for raw in citations or []:
            if not isinstance(raw, dict):
                continue
            key = "|".join(
                str(raw.get(k) or "")[:120]
                for k in ("url", "title", "snippet", "document_id", "source")
            )
            if not key.strip("|") or key in seen:
                continue
            seen.add(key)
            merged.append(dict(raw))
    return merged


def _parse_llm_route_plan(db: Session, data: dict[str, Any] | None) -> AgentRoutePlan | None:
    if not isinstance(data, dict):
        return None
    mode = str(data.get("mode") or "single").strip().lower()
    if mode not in ("single", "sequential", "parallel"):
        mode = "single"
    raw_agents = data.get("agents") or data.get("agent_ids") or []
    if isinstance(raw_agents, str):
        raw_agents = [raw_agents]
    if not isinstance(raw_agents, list):
        return None

    routes: list[AgentRoute] = []
    seen: set[str] = set()
    reason = str(data.get("reason") or "LLM 路由").strip()[:120]
    for raw in raw_agents:
        agent_id = str(raw or "").strip()
        if not agent_id or agent_id in seen:
            continue
        if agent_id not in _LLM_ROUTE_AGENT_IDS:
            continue
        if not is_agent_enabled(db, agent_id):
            continue
        seen.add(agent_id)
        routes.append(
            _pick_route(
                db,
                agent_id,
                reason or _ROUTE_REASONS.get(agent_id, agent_id),
            )
        )
    if not routes:
        return None
    if mode == "single":
        routes = routes[:1]
    return AgentRoutePlan(mode=mode, routes=tuple(routes), source="llm")


async def _llm_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    candidate_routes: list[AgentRoute],
    chat_history: list[AiChatMessage] | None,
) -> AgentRoutePlan | None:
    if not is_configured() or len(candidate_routes) <= 1:
        return None

    catalog = build_supervisor_routing_catalog(db, agent_ids=_LLM_ROUTE_AGENT_IDS)
    candidates = "、".join(f"{r.agent_id}({r.reason})" for r in candidate_routes)
    hist = ""
    for msg in (chat_history or [])[-4:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:160]
        if text:
            hist += f"{role}：{text}\n"

    system = (
        "你是平台调度智能体，负责根据用户诉求与对话上下文选择最合适的专精智能体执行。\n"
        "专精智能体目录：\n"
        f"{catalog}\n\n"
        '返回 JSON：{"mode":"single|sequential|parallel","agents":["agent_id"],"reason":"…"}。\n'
        "规则：\n"
        "- 寒暄/简单心算 → orchestrator\n"
        "- 执行已有上传 Skill 查数据、对话上文刚讨论的技能、短跟贴查价 → skill-dev\n"
        "- 创建/修改 Skill → skill-dev\n"
        "- 知识库正文/联网调研 → research\n"
        "- 平台文档/待办/用户部门 → platform\n"
        "- 多步有先后依赖 → sequential；可同时独立进行 → parallel\n"
        "- agents 必须来自候选列表；选最匹配的一个（除非多步）"
    )
    user_prompt = f"候选：{candidates}\n用户：{(message or '').strip()[:500]}"
    if hist:
        user_prompt = f"近期对话：\n{hist}\n{user_prompt}"

    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.1,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        plan = _parse_llm_route_plan(db, parse_llm_json(content))
        if plan:
            return plan
    except Exception:
        _logger.exception("LLM 多智能体路由失败")
    return None


async def resolve_agent_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> AgentRoutePlan:
    """规则 fast path → 可选 LLM 消歧 → 单/顺序/并行计划。"""
    settings = get_settings()
    rule_routes = _resolve_agent_routes_rule(
        db,
        user,
        message,
        intent_plan=intent_plan,
        chat_history=chat_history,
    )
    mode = _infer_route_mode(message, len(rule_routes))

    if mode == "single" and len(rule_routes) == 1:
        return AgentRoutePlan(mode="single", routes=tuple(rule_routes), source="rule")

    if mode == "sequential" and len(rule_routes) > 1:
        cap = max(1, int(settings.agent_max_sequential_handoffs or 1))
        return AgentRoutePlan(
            mode="sequential",
            routes=tuple(rule_routes[:cap]),
            source="rule",
        )

    if mode == "parallel" and len(rule_routes) > 1:
        cap = max(1, int(settings.agent_max_parallel_handoffs or 1))
        return AgentRoutePlan(
            mode="parallel",
            routes=tuple(rule_routes[:cap]),
            source="rule",
        )

    if (
        settings.agent_routing_llm_enabled
        and len(rule_routes) > 1
        and is_configured()
    ):
        llm_plan = await _llm_route_plan(
            db,
            user,
            message,
            candidate_routes=rule_routes,
            chat_history=chat_history,
        )
        if llm_plan:
            if llm_plan.mode == "sequential":
                cap = max(1, int(settings.agent_max_sequential_handoffs or 1))
                routes = llm_plan.routes[:cap]
            elif llm_plan.mode == "parallel":
                cap = max(1, int(settings.agent_max_parallel_handoffs or 1))
                routes = llm_plan.routes[:cap]
            else:
                routes = llm_plan.routes[:1]
            return AgentRoutePlan(mode=llm_plan.mode, routes=tuple(routes), source="llm")

    return AgentRoutePlan(
        mode="single",
        routes=(_pick_single_route_from_candidates(rule_routes, intent_plan),),
        source="rule",
    )


def resolve_agent_routes(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> list[AgentRoute]:
    """同步规则路由（测试与兼容）。"""
    routes = _resolve_agent_routes_rule(
        db,
        user,
        message,
        intent_plan=intent_plan,
        chat_history=chat_history,
    )
    mode = _infer_route_mode(message, len(routes))
    settings = get_settings()
    if mode == "sequential":
        cap = max(1, int(settings.agent_max_sequential_handoffs or 1))
        return routes[:cap]
    if mode == "parallel":
        cap = max(1, int(settings.agent_max_parallel_handoffs or 1))
        return routes[:cap]
    return [_pick_single_route_from_candidates(routes, intent_plan)] if routes else []


def resolve_agent_route(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> AgentRoute:
    return resolve_agent_routes(
        db,
        user,
        message,
        intent_plan=intent_plan,
        chat_history=chat_history,
    )[0]


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
    async for event in iter_builtin_specialist_hop(sess, user_id, ctx):
        yield event


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


async def _synthesize_from_task_results(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
    screenshot_attachments: list[dict[str, Any]] | None = None,
) -> str:
    """根据各子任务验收摘要生成唯一最终回答。"""
    lines: list[str] = []
    for item in results:
        task = item.task
        if item.satisfied and task.summary:
            lines.append(f"- {task.title}：{task.summary}")
        elif not item.satisfied:
            err = (task.last_error or "未能完成").strip()
            lines.append(f"- {task.title}（未完成）：{err}")
    if not lines:
        return _best_reply_from_hops([item.complete for item in results if item.complete]) or ""

    shot_lines = [
        f"- 页面截图：{str(att.get('url') or '').strip()}"
        for att in list(screenshot_attachments or [])
        if str(att.get("url") or "").strip()
    ]

    if not is_configured():
        merged = "\n".join(lines)
        if shot_lines:
            merged += "\n\n【页面截图】\n" + "\n".join(shot_lines)
        return merged

    try:
        shot_instruction = ""
        if shot_lines:
            shot_instruction = (
                "\n\n【重要】用户要求查看页面截图。子任务已生成以下截图 URL，"
                "请在回答末尾明确写出「页面截图如下」并保留截图信息，"
                "不要省略或仅用文字概括：\n" + "\n".join(shot_lines)
            )
        choice = await chat_completion_message_async(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是企业助手「小析」。根据子任务摘要，写一份面向用户的最终回答（简体中文）。\n"
                        + assistant_user_communication_style()
                        + "\n"
                        + assistant_conclusion_source_priority()
                        + "\n【用户记忆】有助手名称则用该名称自称。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        (f"{memory_context.strip()}\n\n" if memory_context.strip() else "")
                        + f"用户诉求：{user_message.strip()[:800]}\n\n"
                        f"子任务结果：\n" + "\n".join(lines)
                        + shot_instruction
                    ),
                },
            ],
            tools=None,
            temperature=0.4,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        if content:
            return content
    except Exception:
        _logger.exception("任务结果汇总失败")
    merged = "\n".join(lines)
    if shot_lines:
        merged += "\n\n【页面截图】\n" + "\n".join(shot_lines)
    return merged


async def _build_orchestrator_final_reply(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
) -> tuple[str | None, list[dict[str, Any]]]:
    """构建编排终稿：有浏览器截图时保留专精结果，避免汇总 LLM 丢掉截图。"""
    from app.services.agent_skill_router import (
        is_org_member_list_question,
        is_platform_system_data_message,
        user_wants_browser_screenshot,
    )

    screenshot_attachments = collect_screenshot_attachments_from_task_results(results)
    hop_reply = _best_reply_from_hops(
        [item.complete for item in results if item.complete and item.satisfied]
    )

    if hop_reply and (
        is_org_member_list_question(user_message)
        or is_platform_system_data_message(user_message)
    ):
        final_reply = append_screenshot_markdown_to_reply(hop_reply, screenshot_attachments)
        return final_reply, screenshot_attachments

    if screenshot_attachments and user_wants_browser_screenshot(user_message):
        body = (hop_reply or "").strip()
        if not body:
            body = "已完成您要求的浏览器操作，页面截图如下。"
        final_reply = append_screenshot_markdown_to_reply(body, screenshot_attachments)
        return final_reply, screenshot_attachments

    if hop_reply and results and all(item.satisfied for item in results):
        final_reply = append_screenshot_markdown_to_reply(hop_reply, screenshot_attachments)
        return final_reply, screenshot_attachments

    final_reply = await _synthesize_from_task_results(
        user_message,
        results,
        memory_context=memory_context,
        screenshot_attachments=screenshot_attachments,
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

    for attempt in range(1, MAX_TASK_ATTEMPTS + 1):
        task.attempts = attempt
        if attempt > 1:
            yield workflow_task_event(
                "task_retry",
                task,
                step_id=step_id,
                detail=task.last_error,
                attempt=attempt,
                all_tasks=all_tasks,
            )
            attempt_message = build_retry_user_message(
                user_message, task, task.last_error
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
) -> AsyncIterator[dict[str, Any]]:
    """子任务编排：可选任务清单 → 专精执行 → 调度汇总答复用户。"""
    conv_key = (conversation_id or "").strip() or f"ephemeral-{uuid.uuid4().hex[:8]}"
    tasks = tasks_from_routes(routes)
    plan_id = new_plan_step_id()
    bus = get_session_bus()
    bus.reset(conv_key)
    if not skip_plan_ui:
        yield workflow_plan_tasks(tasks, step_id=plan_id, mode=mode)

    if mode == "parallel":
        async for event in _execute_parallel_task_workers(
            routes,
            tasks=tasks,
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
        ):
            yield event
        return

    results: list[TaskExecutionResult] = []
    hop_completes: list[dict[str, Any] | None] = []
    hop_message = user_message

    for task_idx, (task, route) in enumerate(zip(tasks, routes, strict=True)):
        if task_idx > 0:
            hop_message = bus.format_task_request_for_llm(
                session_id=conv_key,
                task_id=task.id,
                target_agent_id=route.agent_id,
                user_message=user_message,
            )

        result: TaskExecutionResult | None = None
        async for event in _iter_one_orchestrated_task(
            sess=sess,
            user_id=user_id,
            task=task,
            route=route,
            user_message=hop_message,
            chat_history=chat_history,
            retrieval_context=retrieval_context if task_idx == 0 else "",
            context_instruction=context_instruction if task_idx == 0 else "",
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            max_rounds=max_rounds,
            conv_key=conv_key,
            all_tasks=tasks,
        ):
            if event.get("type") == _ORCH_TASK_RESULT:
                result = event["result"]
                continue
            yield event
        if result is not None:
            results.append(result)
        if result and result.complete:
            hop_completes.append(result.complete)

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
) -> AsyncIterator[dict[str, Any]]:
    """并行执行各子任务，合并事件流。"""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    results: list[TaskExecutionResult] = []

    async def worker(task: OrchestratorTask, route: AgentRoute) -> None:
        worker_sess = AgentLoopSession(user_id)
        try:
            result: TaskExecutionResult | None = None
            async for event in _iter_one_orchestrated_task(
                sess=worker_sess,
                user_id=user_id,
                task=task,
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
                conv_key=conv_key,
                all_tasks=tasks,
            ):
                if event.get("type") == _ORCH_TASK_RESULT:
                    result = event["result"]
                    continue
                await queue.put(event)
            if result is not None:
                await queue.put(("_result", result))
        except Exception:
            _logger.exception("并行子任务失败 task=%s", task.id)
            task.status = "failed"
            task.last_error = "子任务执行异常"
            await queue.put(
                workflow_task_event(
                    "task_failed",
                    task,
                    step_id=new_task_step_id(task.id),
                    detail=task.last_error,
                    all_tasks=tasks,
                )
            )
        finally:
            worker_sess.close()
            await queue.put("_done")

    workers = [
        asyncio.create_task(worker(task, route))
        for task, route in zip(tasks, routes, strict=True)
    ]
    active = len(workers)
    while active > 0:
        item = await queue.get()
        if item == "_done":
            active -= 1
            continue
        if isinstance(item, tuple) and item[0] == "_result":
            results.append(item[1])
            continue
        yield item

    await asyncio.gather(*workers, return_exceptions=True)
    hop_completes = [r.complete for r in results if r.complete]
    async for event in _yield_orchestrator_synthesis(
        user_message,
        results,
        user_id=user_id,
        messages=messages,
        hop_completes=hop_completes,
    ):
        yield event


async def _yield_orchestrator_synthesis(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    user_id: int,
    messages: list[dict[str, Any]],
    hop_completes: list[dict[str, Any] | None],
) -> AsyncIterator[dict[str, Any]]:
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
    final_reply, screenshot_attachments = await _build_orchestrator_final_reply(
        user_message,
        results,
        memory_context=build_memory_prompt_context(user_id),
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
    conv_key = (conversation_id or "").strip() or f"ephemeral-{uuid.uuid4().hex[:8]}"
    routes = list(plan.routes)
    if not routes:
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
            context_instruction=context_instruction,
            mode=plan.mode if plan.mode in ("sequential", "parallel") else "sequential",
            skip_plan_ui=False,
        ):
            yield event
        return

    if _is_direct_conversation_fast_path(user_message, routes[0], chat_history):
        from app.services.agent_tool_loop import iter_agent_tool_loop

        async for event in iter_agent_tool_loop(
            user_id,
            messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            agent_id="orchestrator",
        ):
            yield event
        return

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
        context_instruction=context_instruction,
        mode="sequential",
        skip_plan_ui=False,
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
) -> AsyncIterator[dict[str, Any]]:
    """Supervisor 入口：单路由 / 顺序 handoff / 并行 handoff。"""
    from app.services.agent_tool_loop import iter_agent_tool_loop

    user_id = coerce_user_id(user)
    settings = get_settings()
    if not settings.agent_multi_agent_enabled:
        async for event in iter_agent_tool_loop(
            user_id,
            messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
        ):
            yield event
        return

    route_plan_step_id = f"route-plan-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "正在规划方案",
            "detail": "",
            "tool": "supervisor.plan",
            "step_id": route_plan_step_id,
            "agent_id": "orchestrator",
            "agent_title": "小析调度",
        },
    }

    sess = AgentLoopSession(user_id)
    db, bound_user = sess.open()
    try:
        plan = await resolve_agent_route_plan(
            db,
            bound_user,
            user_message,
            intent_plan=intent_plan,
            chat_history=chat_history,
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
    plan_detail = "\n".join(route_details[:4]) if route_details else "、".join(route_titles[:4])
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

    async for event in _execute_route_plan(
        plan,
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
        context_instruction=context_instruction,
    ):
        yield event
