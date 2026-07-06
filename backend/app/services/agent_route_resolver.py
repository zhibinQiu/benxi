"""智能体路由解析 — 从 Supervisor 抽离的 Skill/LLM 路由逻辑。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from agentkit_route import filter_routes_by_agent_scores
from app.config import get_settings
from app.core.agent.routing import (
    build_route_plan,
    infer_route_mode,
    pick_route,
    plan_orchestrator_direct,
    should_use_llm_routing,
)
from app.core.agent.types import ROUTE_REASONS, AgentRoute, AgentRoutePlan
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import AgentToolPlan, should_orchestrator_reply_directly
from app.services.agent_routing_signals import (
    is_compound_parallel_message,
    is_compound_sequential_message,
)


def resolve_agent_routes_from_skills(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
) -> list[AgentRoute]:
    """Skill 召回聚合专精 Agent；寒暄/简单问题走调度直答。"""
    msg = (message or "").strip()
    if not msg:
        return [pick_route(db, "orchestrator", ROUTE_REASONS["orchestrator"])]
    if should_orchestrator_reply_directly(msg, chat_history):
        return [pick_route(db, "orchestrator", ROUTE_REASONS["orchestrator"])]

    from app.services.agent_routing_catalog import message_targets_uploaded_skill
    from app.services.agent_skill_routing import (
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
        skill_route_reason,
    )

    if message_targets_uploaded_skill(db, user, msg, chat_history):
        return [pick_route(db, "skill-dev", "发展技能执行")]

    from app.services.agent_routing_signals import (
        matches_search_rpa_browser_intent,
        matches_search_rpa_research_intent,
    )

    if matches_search_rpa_browser_intent(msg):
        return [pick_route(db, "rpa", ROUTE_REASONS["rpa"])]
    if matches_search_rpa_research_intent(msg):
        return [pick_route(db, "orchestrator", "通用检索由 orchestrator 处理")]

    scores = pick_skill_route_scores(
        resolve_skill_routed_agent_scores(
            db, user, message, prior_outcomes=prior_outcomes
        ),
        query=msg,
    )
    if not scores:
        return [pick_route(db, "orchestrator", "无匹配Skill")]

    routes = [
        pick_route(db, item.agent_id, skill_route_reason(item))
        for item in scores
    ]

    if is_compound_sequential_message(msg) or is_compound_parallel_message(msg):
        return routes

    if len(routes) == 1:
        return routes

    top_score = scores[0].score
    by_id = {item.agent_id: item.score for item in scores}
    return filter_routes_by_agent_scores(routes, by_id, top_score=top_score)


def pick_single_route_from_candidates(
    routes: list[AgentRoute],
    _intent_plan: AgentToolPlan | None = None,
) -> AgentRoute:
    if not routes:
        raise ValueError("routes must not be empty")
    return routes[0]


async def resolve_agent_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    force_replan: bool = False,
) -> AgentRoutePlan:
    """Skill 关键词路由 + 能力兜底；寒暄/简单问题调度直答。"""
    from app.services.agent_capability_fallback import resolve_capability_gap_route_plan
    from app.services.agent_skill_match import assess_skill_match
    from app.services.agent_skill_routing import llm_plan_routes_from_skills

    settings = get_settings()
    msg = (message or "").strip()
    if not msg:
        return plan_orchestrator_direct(db)
    if should_orchestrator_reply_directly(msg, chat_history):
        return plan_orchestrator_direct(db)

    outcomes = prior_outcomes if (force_replan or prior_outcomes) else None

    from app.services.agent_routing_catalog import message_targets_uploaded_skill

    if message_targets_uploaded_skill(db, user, msg, chat_history):
        return AgentRoutePlan(
            mode="single",
            routes=(pick_route(db, "skill-dev", "发展技能执行"),),
            source="skill",
        )

    # 首次调用走关键词路由，跳过 LLM 路由（retry 时再用 LLM 兜底）
    if not prior_outcomes and not force_replan:
        routes = resolve_agent_routes_from_skills(
            db, user, message, chat_history=chat_history
        )
        mode = infer_route_mode(message, len(routes), settings=settings)
        if mode == "single" and len(routes) == 1:
            return AgentRoutePlan(mode="single", routes=tuple(routes), source="skill_keyword")
        return build_route_plan(mode, routes, source="skill_keyword", settings=settings)

    assessment = assess_skill_match(db, user, msg, prior_outcomes=outcomes)
    strict = (settings.agent_capability_fallback_mode or "loose").strip().lower() == "strict"

    def gap_pick(d, u, m, **kw):
        return resolve_agent_routes_from_skills(
            d, u, m, chat_history=kw.get("chat_history"), prior_outcomes=outcomes
        )

    if assessment.kind in ("none", "weak") or (assessment.kind == "partial" and strict):
        plan, _ = await resolve_capability_gap_route_plan(
            db,
            user,
            msg,
            assessment,
            chat_history=chat_history,
            pick_routes=gap_pick,
            pick_route=pick_route,
            route_reasons=ROUTE_REASONS,
        )
        return plan
    if assessment.kind == "partial":
        plan, _ = await resolve_capability_gap_route_plan(
            db,
            user,
            msg,
            assessment,
            chat_history=chat_history,
            pick_routes=gap_pick,
            pick_route=pick_route,
            route_reasons=ROUTE_REASONS,
        )
        if plan.source == "capability_partial":
            return plan

    if should_use_llm_routing(
        db, user, msg, force_replan=force_replan, prior_outcomes=outcomes
    ):
        resolved = await llm_plan_routes_from_skills(
            db,
            user,
            message,
            chat_history=chat_history,
            prior_outcomes=outcomes,
        )
        if resolved is not None:
            routes = [
                pick_route(db, agent_id, reason)
                for agent_id, reason in resolved.items
            ]
            source = "llm_skill_replan" if force_replan else "llm_skill"
            return build_route_plan(resolved.mode, routes, source=source, settings=settings)

    routes = resolve_agent_routes_from_skills(
        db,
        user,
        message,
        chat_history=chat_history,
        prior_outcomes=outcomes,
    )
    mode = infer_route_mode(message, len(routes), settings=settings)
    if mode == "single" and len(routes) == 1:
        return AgentRoutePlan(mode="single", routes=tuple(routes), source="skill_keyword")
    return build_route_plan(mode, routes, source="skill_keyword", settings=settings)


def resolve_agent_routes(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> list[AgentRoute]:
    """同步 Skill 路由（测试与兼容）。"""
    routes = resolve_agent_routes_from_skills(
        db,
        user,
        message,
        chat_history=chat_history,
    )
    mode = infer_route_mode(message, len(routes))
    if mode == "single" or len(routes) <= 1:
        return [pick_single_route_from_candidates(routes, intent_plan)] if routes else []
    return routes


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
