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
from app.core.agent_profiles import AGENT_PROFILES, get_agent_profile
from app.core.agent_resident import build_specialist_resident_prompt
from app.core.llm_parse import parse_llm_json
from app.core.prompt_budget import build_bounded_chat_messages
from app.database import SessionLocal
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    AgentToolPlan,
    is_chitchat_message,
    needs_knowledge_retrieval,
)
from app.services.agent_memory_service import build_memory_prompt_context
from app.services.agent_orchestrator import (
    MAX_TASK_ATTEMPTS,
    TaskExecutionResult,
    build_retry_user_message,
    new_plan_step_id,
    new_task_step_id,
    tasks_from_routes,
    verify_task_result,
    workflow_plan_tasks,
    workflow_task_event,
)
from app.services.agent_profile_service import (
    is_agent_enabled,
    resolve_agent_skill_names,
    resolve_agent_tool_names,
)
from app.services.agent_runtime_service import mark_agent_idle, mark_agent_running
from app.services.agent_skill_router import (
    _PAGE_INTENT_RE,
    _URL_IN_MESSAGE_RE,
    is_platform_usage_message,
    is_skill_management_message,
)
from app.services.assistant_knowledge import build_platform_knowledge
from app.skills.catalog import build_agent_catalog_prompt

_logger = logging.getLogger(__name__)

RouteMode = Literal["single", "sequential", "parallel"]

_PLATFORM_OPS_RE = re.compile(
    r"(文档库|文件夹|我的文件|待办|todo|记一下|加个待办|"
    r"list_document|list_library|list_manageable|rename_document|"
    r"move_document|share_document|delete_document|send_notification|"
    r"上传.{0,6}文档|分享.{0,4}文档|重命名|移动到)",
    re.I,
)
_SCHEDULER_RE = re.compile(
    r"(定时任务|定时执行|定时提醒|取消定时|列出.*定时|"
    r"schedule_browser|list_scheduled_notifications|cancel_scheduled_notification|"
    r"延迟提醒|cron)",
    re.I,
)
_BROWSER_RE = re.compile(
    r"(browser_|网页|网站|页面|截图|截屏|RPA|workflow|"
    r"browser_navigate|browser_snapshot|browser_click|点击|填表|浏览器自动化|"
    r"打开.{0,4}(?:网页|网站|链接))",
    re.I,
)
_RESEARCH_RE = re.compile(
    r"(知识库|检索|搜索|联网|上网|图谱|实体|"
    r"knowledge_retrieve|web_search|kg_query|最新|新闻|政策)",
    re.I,
)
_COMPOUND_SEQ_RE = re.compile(
    r"(?:先|首先).{0,24}(?:然后|接着|之后|再)|"
    r"(?:然后|接着|之后|再).{0,24}(?:创建|添加|移动|分享|提醒|待办|定时)",
    re.I,
)
_COMPOUND_PARALLEL_RE = re.compile(
    r"(?:同时|一并|顺便|以及|还有|并且).{0,20}(?:查|检索|搜索|待办|定时|提醒|列表|文件夹)|"
    r"(?:查|检索|搜索).{0,24}(?:同时|顺便|以及|还有).{0,24}(?:待办|定时|提醒|列表|文件夹)",
    re.I,
)
_TRIVIAL_DIRECT_RE = re.compile(
    r"^[\d\s\+\-\*/\(\)\.=]{2,}(?:等于|是)?\s*多少",
    re.I,
)

_ROUTE_EXECUTION_ORDER = ("research", "platform", "scheduler", "rpa")
_HOP_CLIENT_PREVIEW_TYPES = frozenset({"replace", "delta"})


def _skip_hop_client_preview(event: dict[str, Any]) -> bool:
    """多智能体 hop 的中间回答仅用于 handoff，不下发前端（避免覆盖与二次闪烁）。"""
    return event.get("type") in _HOP_CLIENT_PREVIEW_TYPES


_ROUTE_REASONS: dict[str, str] = {
    "research": "资料检索 / 知识问答",
    "platform": "平台文档 / 待办 / 通知",
    "scheduler": "定时任务 / 延迟提醒",
    "rpa": "浏览器 / 网页交互",
    "skill-dev": "Skill 创建/更新/删除",
    "orchestrator": "日常交流",
}
_LLM_ROUTE_AGENT_IDS = frozenset(
    {"orchestrator", "platform", "research", "rpa", "scheduler", "skill-dev"}
)
_SINGLE_ROUTE_PRIORITY = ("platform", "scheduler", "rpa", "research")


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
    text = (msg or "").strip()
    if not text or len(text) > 48:
        return False
    if _RESEARCH_RE.search(text) or _PLATFORM_OPS_RE.search(text):
        return False
    return bool(_TRIVIAL_DIRECT_RE.match(text))


def _domain_flags(
    db: Session,
    msg: str,
    *,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
) -> dict[str, bool]:
    plan = intent_plan
    skill_dev = is_skill_management_message(msg)
    rpa = bool(
        _BROWSER_RE.search(msg)
        or _URL_IN_MESSAGE_RE.search(msg)
        or _PAGE_INTENT_RE.search(msg)
    ) and bool(resolve_agent_tool_names(db, "rpa"))
    scheduler = bool(_SCHEDULER_RE.search(msg))
    if plan and plan.intent_label == "设置定时提醒":
        scheduler = True
    platform = bool(is_platform_usage_message(msg) or _PLATFORM_OPS_RE.search(msg))
    if plan and plan.intent_label == "解答平台使用问题":
        platform = True
    explicit_research = bool(
        _RESEARCH_RE.search(msg)
        or (plan and plan.use_attachment)
        or (
            needs_knowledge_retrieval(msg, chat_history)
            and not _PLATFORM_OPS_RE.search(msg)
            and not _is_trivial_direct_question(msg)
        )
    )
    # 路由到 research 须为明确检索意图；勿将「默认倾向联网」误判为专精路由。
    research = explicit_research
    if platform and research and _PLATFORM_OPS_RE.search(msg) and not _RESEARCH_RE.search(msg):
        research = False
    orchestrator = bool(
        (plan and plan.intent_label == "日常交流，直接回答")
        or is_chitchat_message(msg)
    )
    return {
        "skill-dev": skill_dev,
        "rpa": rpa,
        "scheduler": scheduler,
        "platform": platform,
        "research": research,
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
        text = str((event or {}).get("reply") or "").strip()
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
    flags = _domain_flags(db, msg, intent_plan=intent_plan, chat_history=chat_history)

    if flags["skill-dev"]:
        return [_pick_route(db, "skill-dev", _ROUTE_REASONS["skill-dev"])]

    others_active = any(flags[k] for k in _ROUTE_EXECUTION_ORDER)
    if flags["orchestrator"] and not others_active:
        return [_pick_route(db, "orchestrator", _ROUTE_REASONS["orchestrator"])]

    ordered_ids: list[str] = [
        agent_id for agent_id in _ROUTE_EXECUTION_ORDER if flags.get(agent_id)
    ]
    if not ordered_ids:
        if flags["orchestrator"]:
            return [_pick_route(db, "orchestrator", _ROUTE_REASONS["orchestrator"])]
        return [_pick_route(db, "orchestrator", "日常问答（默认调度智能体）")]

    return [
        _pick_route(db, agent_id, _ROUTE_REASONS.get(agent_id, agent_id))
        for agent_id in ordered_ids
    ]


def _infer_route_mode(message: str, route_count: int) -> RouteMode:
    if route_count <= 1:
        return "single"
    msg = (message or "").strip()
    if _COMPOUND_SEQ_RE.search(msg):
        return "sequential"
    settings = get_settings()
    if (
        settings.agent_parallel_handoff_enabled
        and _COMPOUND_PARALLEL_RE.search(msg)
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

    catalog = "、".join(
        f"{p.id}({p.title})"
        for p in sorted(AGENT_PROFILES, key=lambda item: item.sort_order)
        if p.id in _LLM_ROUTE_AGENT_IDS
    )
    candidates = "、".join(f"{r.agent_id}({r.reason})" for r in candidate_routes)
    hist = ""
    for msg in (chat_history or [])[-2:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:100]
        if text:
            hist += f"{role}：{text}\n"

    system = (
        f"调度器。智能体：{catalog}。"
        '返回 JSON：{"mode":"single|sequential","agents":["research"],"reason":"…"}。'
        "寒暄→orchestrator；多步→sequential；否则选最匹配一个。agents 仅限候选。"
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


def build_specialist_chat_messages(
    db: Session,
    user: User,
    *,
    agent_id: str,
    message: str,
    history: list[AiChatMessage] | None,
    retrieval_context: str = "",
    context_instruction: str = "",
    task_mode: bool = False,
) -> list[dict[str, Any]]:
    from app.services.agent_context_service import _needs_platform_knowledge

    skill_names = resolve_agent_skill_names(db, agent_id)
    skill_catalog = build_agent_catalog_prompt(
        db,
        user=user,
        skill_names=skill_names,
    )
    platform_knowledge = ""
    if agent_id == "platform" and _needs_platform_knowledge(message):
        platform_knowledge = build_platform_knowledge(db, user)

    trimmed_history = list(history or [])
    if agent_id != "orchestrator" and len(trimmed_history) > 6:
        trimmed_history = trimmed_history[-6:]

    from app.services.agent_profile_service import resolve_agent_instruction_body

    config_body = resolve_agent_instruction_body(db, agent_id)
    memory_context = build_memory_prompt_context(user.id)

    return build_bounded_chat_messages(
        system=build_specialist_resident_prompt(
            agent_id, config_body=config_body, task_mode=task_mode
        ),
        history=trimmed_history,
        user_message=message,
        retrieval_context=retrieval_context,
        platform_knowledge=platform_knowledge,
        skill_catalog=skill_catalog,
        memory_context=memory_context,
        context_instruction=context_instruction or "",
    )


def _handoff_user_message(original: str, prior_reply: str, agent_id: str) -> str:
    profile = get_agent_profile(agent_id)
    title = profile.title if profile else agent_id
    summary = (prior_reply or "").strip()[:2000]
    return (
        f"{original.strip()}\n\n"
        f"【{title} · 前置结果】\n{summary}\n\n"
        "请完成你负责的步骤并调用工具。"
    )


def _annotate_workflow(event: dict[str, Any], *, agent_id: str, agent_title: str) -> dict[str, Any]:
    if event.get("type") != "workflow":
        return event
    data = dict(event.get("data") or {})
    data["agent_id"] = agent_id
    data["agent_title"] = agent_title
    return {"type": "workflow", "data": data}


async def _run_specialist_hop(
    db: Session,
    user: User,
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
) -> AsyncIterator[dict[str, Any]]:
    profile = get_agent_profile(route.agent_id)
    agent_title = profile.title if profile else route.agent_id

    route_step_id = f"agent-route-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": agent_title,
            "detail": route.reason,
            "tool": "supervisor.route",
            "step_id": route_step_id,
            "status": "done",
            "agent_id": route.agent_id,
            "agent_title": agent_title,
        },
    }

    working_messages = build_specialist_chat_messages(
        db,
        user,
        agent_id=route.agent_id,
        message=user_message,
        history=chat_history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
        task_mode=task_mode,
    )

    allowed_tools = resolve_agent_tool_names(db, route.agent_id)
    skill_names = resolve_agent_skill_names(db, route.agent_id)
    allowed_skills = set(skill_names)

    settings = get_settings()
    if route.agent_id == "orchestrator":
        specialist_rounds = min(8, max_rounds or 8)
    else:
        specialist_rounds = min(
            settings.agent_specialist_max_tool_rounds,
            max_rounds or settings.agent_specialist_max_tool_rounds,
        )

    from app.services.agent_tool_loop import iter_agent_tool_loop

    async for event in iter_agent_tool_loop(
        db,
        user,
        working_messages,
        conversation_id=conversation_id,
        max_rounds=specialist_rounds,
        user_message=user_message,
        attachment_session_id=attachment_session_id,
        tools=tools,
        intent_plan=intent_plan,
        chat_history=chat_history,
        agent_id=route.agent_id,
        allowed_tool_names=allowed_tools,
        allowed_skill_names=allowed_skills,
    ):
        yield _annotate_workflow(
            event,
            agent_id=route.agent_id,
            agent_title=agent_title,
        )


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
    profile = get_agent_profile(agent_id)
    return profile.title if profile else agent_id


async def _synthesize_from_task_results(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    memory_context: str = "",
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
        return _best_reply_from_hops([item.complete for item in results if item.complete])

    if not is_configured():
        return "\n".join(lines)

    try:
        choice = await chat_completion_message_async(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "根据子任务摘要写一份简短最终结论（简体中文）。"
                        "只答用户所问，不重复过程，不加额外建议。"
                        "【用户记忆】有助手名称则用该名称自称。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        (f"{memory_context.strip()}\n\n" if memory_context.strip() else "")
                        + f"用户诉求：{user_message.strip()[:800]}\n\n"
                        f"子任务结果：\n" + "\n".join(lines)
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
    return "\n".join(lines)


async def _execute_orchestrated_tasks(
    routes: list[AgentRoute],
    *,
    db: Session,
    user: User,
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
    """多子任务顺序编排：规划清单 → 逐步执行/验收/重试 → 最终汇总。"""
    conv_key = (conversation_id or "").strip() or f"ephemeral-{uuid.uuid4().hex[:8]}"
    tasks = tasks_from_routes(routes)
    plan_id = new_plan_step_id()
    yield workflow_plan_tasks(tasks, step_id=plan_id)

    results: list[TaskExecutionResult] = []
    hop_completes: list[dict[str, Any] | None] = []
    hop_message = user_message

    for task_idx, (task, route) in enumerate(zip(tasks, routes, strict=True)):
        task.status = "running"
        step_id = new_task_step_id(task.id)
        yield workflow_task_event(
            "task_started", task, step_id=step_id, all_tasks=tasks
        )

        if task_idx > 0:
            done_lines = [
                f"- {r.task.title}：{r.task.summary}"
                for r in results
                if r.satisfied and r.task.summary
            ]
            if done_lines:
                hop_message = (
                    f"{user_message.strip()}\n\n【已完成】\n" + "\n".join(done_lines)
                )

        satisfied = False
        events: list[dict[str, Any]] = []
        complete: dict[str, Any] | None = None
        attempt_message = hop_message

        for attempt in range(1, MAX_TASK_ATTEMPTS + 1):
            task.attempts = attempt
            if attempt > 1:
                yield workflow_task_event(
                    "task_retry",
                    task,
                    step_id=step_id,
                    detail=task.last_error,
                    attempt=attempt,
                    all_tasks=tasks,
                )
                attempt_message = build_retry_user_message(
                    user_message, task, task.last_error
                )

            mark_agent_running(route.agent_id, conv_key)
            try:
                hop_events: list[dict[str, Any]] = []
                async for event in _run_specialist_hop(
                    db,
                    user,
                    route=route,
                    user_message=attempt_message,
                    chat_history=chat_history,
                    retrieval_context=retrieval_context if task_idx == 0 else "",
                    context_instruction=context_instruction if task_idx == 0 else "",
                    conversation_id=conversation_id,
                    attachment_session_id=attachment_session_id,
                    tools=tools,
                    intent_plan=intent_plan,
                    max_rounds=max_rounds,
                    task_mode=True,
                ):
                    if event.get("type") == "complete":
                        complete = event
                    else:
                        hop_events.append(event)
            finally:
                mark_agent_idle(route.agent_id, conv_key)

            events = hop_events
            for event in events:
                if _skip_hop_client_preview(event):
                    continue
                yield event

            satisfied, summary, retry_hint = verify_task_result(
                task, events, complete
            )
            if satisfied:
                task.status = "done"
                task.summary = summary
                yield workflow_task_event(
                    "task_done",
                    task,
                    step_id=step_id,
                    detail=summary,
                    all_tasks=tasks,
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
                all_tasks=tasks,
            )

        results.append(
            TaskExecutionResult(
                task=task,
                route=route,
                events=events,
                complete=complete,
                satisfied=satisfied,
            )
        )
        if complete:
            hop_completes.append(complete)

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
    final_reply = await _synthesize_from_task_results(
        user_message,
        results,
        memory_context=build_memory_prompt_context(user.id),
    )
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
    db: Session,
    user: User,
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
            db=db,
            user=user,
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
        return

    hop_message = user_message
    prior_reply = ""
    hop_completes: list[dict[str, Any] | None] = []
    yielded_final = False

    for hop_idx, route in enumerate(routes):
        is_last = hop_idx >= len(routes) - 1
        if prior_reply:
            hop_message = _handoff_user_message(user_message, prior_reply, route.agent_id)

        mark_agent_running(route.agent_id, conv_key)
        try:
            async for event in _run_specialist_hop(
                db,
                user,
                route=route,
                user_message=hop_message,
                chat_history=chat_history,
                retrieval_context=retrieval_context if hop_idx == 0 else "",
                context_instruction=context_instruction if hop_idx == 0 else "",
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                tools=tools,
                intent_plan=intent_plan,
                max_rounds=max_rounds,
            ):
                if event.get("type") == "complete":
                    hop_completes.append(event)
                    hop_reply = str(event.get("reply") or "").strip()
                    if hop_reply:
                        prior_reply = hop_reply
                    if is_last:
                        merged = _build_final_complete(
                            messages=messages,
                            hop_completes=hop_completes,
                            reply=_best_reply_from_hops(hop_completes),
                        )
                        yield merged
                        yielded_final = True
                else:
                    if not is_last and _skip_hop_client_preview(event):
                        continue
                    yield event
        finally:
            mark_agent_idle(route.agent_id, conv_key)

    if not yielded_final:
        yield _build_final_complete(
            messages=messages,
            hop_completes=hop_completes,
            reply=_best_reply_from_hops(hop_completes),
        )


async def iter_supervised_agent_loop(
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
    retrieval_context: str = "",
    context_instruction: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Supervisor 入口：单路由 / 顺序 handoff / 并行 handoff。"""
    from app.services.agent_tool_loop import iter_agent_tool_loop

    settings = get_settings()
    if not settings.agent_multi_agent_enabled:
        async for event in iter_agent_tool_loop(
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
        ):
            yield event
        return

    plan = await resolve_agent_route_plan(
        db,
        user,
        user_message,
        intent_plan=intent_plan,
        chat_history=chat_history,
    )

    async for event in _execute_route_plan(
        plan,
        db=db,
        user=user,
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
