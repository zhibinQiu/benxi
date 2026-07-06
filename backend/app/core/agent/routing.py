"""智能体路由 — 评分、模糊判定、handoff 上限（agentkit-route + 平台 DB/配置）。"""

from __future__ import annotations

from agentkit_route import RouteLimits, build_route_plan as _build_route_plan
from agentkit_route import cap_routes as _cap_routes
from agentkit_route import infer_route_mode as _infer_route_mode
from agentkit_route import pick_route_with_fallback
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.agent.types import AgentRoute, AgentRoutePlan, RouteMode, ROUTE_REASONS
from app.models.org import User
from app.services.agent_profile_service import is_agent_enabled
from app.services.agent_routing_signals import (
    is_compound_parallel_message,
    is_compound_sequential_message,
)


def _route_limits(settings: Settings | None = None) -> RouteLimits:
    cfg = settings or get_settings()
    return RouteLimits(
        max_sequential_handoffs=max(1, int(cfg.agent_max_sequential_handoffs or 1)),
        max_parallel_handoffs=max(1, int(cfg.agent_max_parallel_handoffs or 1)),
    )


def pick_route(db: Session, agent_id: str, reason: str) -> AgentRoute:
    return pick_route_with_fallback(
        agent_id,
        reason,
        is_enabled=lambda aid: is_agent_enabled(db, aid),
    )


def plan_orchestrator_direct(db: Session, reason: str | None = None) -> AgentRoutePlan:
    note = reason or ROUTE_REASONS["orchestrator"]
    return AgentRoutePlan(
        mode="single",
        routes=(pick_route(db, "orchestrator", note),),
        source="direct",
    )


def infer_route_mode(message: str, route_count: int, *, settings: Settings | None = None) -> RouteMode:
    return _infer_route_mode(
        message,
        route_count,
        limits=_route_limits(settings),
        is_sequential=is_compound_sequential_message,
        is_parallel=is_compound_parallel_message,
    )


def cap_routes(mode: RouteMode, routes: list[AgentRoute], *, settings: Settings | None = None) -> list[AgentRoute]:
    return _cap_routes(mode, routes, limits=_route_limits(settings))


def build_route_plan(
    mode: RouteMode,
    routes: list[AgentRoute],
    *,
    source: str,
    settings: Settings | None = None,
) -> AgentRoutePlan:
    return _build_route_plan(mode, routes, source=source, limits=_route_limits(settings))


def is_routing_ambiguous(
    db: Session,
    user: User,
    message: str,
    *,
    prior_outcomes: list[str] | None = None,
) -> bool:
    """Skill 关键词路由置信度低或多专精分数接近。"""
    from app.services.agent_skill_routing import (
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
    )

    msg = (message or "").strip()
    if is_compound_sequential_message(msg) or is_compound_parallel_message(msg):
        return False
    scores = resolve_skill_routed_agent_scores(
        db, user, message, prior_outcomes=prior_outcomes
    )
    picked = pick_skill_route_scores(scores, query=msg)
    if not picked:
        return True
    if len(picked) == 1:
        return picked[0].score <= 1.5
    return picked[1].score >= picked[0].score * 0.7


def should_use_llm_routing(
    db: Session,
    user: User,
    message: str,
    *,
    force_replan: bool,
    prior_outcomes: list[str] | None = None,
) -> bool:
    if not get_settings().agent_routing_llm_enabled:
        return False
    return force_replan or is_routing_ambiguous(
        db, user, message, prior_outcomes=prior_outcomes
    )
