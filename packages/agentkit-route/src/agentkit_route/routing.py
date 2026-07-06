"""智能体路由 — 模式推断、handoff 上限与计划构建（纯函数，零平台依赖）。"""

from __future__ import annotations

from dataclasses import dataclass

from agentkit_route.signals import CompoundDetector, never_detected
from agentkit_route.types import AgentRoute, AgentRoutePlan, RouteMode


@dataclass(frozen=True, slots=True)
class RouteLimits:
    """路由上限配置；由宿主注入。"""

    max_sequential_handoffs: int = 3
    max_parallel_handoffs: int = 2


def pick_route_with_fallback(
    agent_id: str,
    reason: str,
    *,
    is_enabled: CompoundDetector,
    fallback_agent_id: str = "orchestrator",
) -> AgentRoute:
    """若 agent 未启用则回退到 fallback（通常为 orchestrator）。"""
    if is_enabled(agent_id):
        return AgentRoute(agent_id=agent_id, reason=reason)
    return AgentRoute(
        agent_id=fallback_agent_id,
        reason=f"{reason}（{agent_id} 已禁用，由调度智能体处理）",
    )


def infer_route_mode(
    message: str,
    route_count: int,
    *,
    limits: RouteLimits | None = None,
    is_sequential: CompoundDetector | None = None,
    is_parallel: CompoundDetector | None = None,
) -> RouteMode:
    """根据消息特征与路由数量推断 single / sequential / parallel。

    ``is_sequential`` / ``is_parallel`` 由宿主注入（如语言匹配、LLM 分类）。
    未注入时仅根据 route_count 决策。
    """
    if route_count <= 1:
        return "single"
    if is_sequential is not None and is_sequential(message):
        return "sequential"
    cfg = limits or RouteLimits()
    if cfg.max_parallel_handoffs > 0 and is_parallel is not None and is_parallel(message):
        return "parallel"
    return "sequential"


def cap_routes(
    mode: RouteMode,
    routes: list[AgentRoute],
    *,
    limits: RouteLimits | None = None,
) -> list[AgentRoute]:
    """按模式截断 handoff 数量，防止 token / 成本爆炸。"""
    cfg = limits or RouteLimits()
    if not routes:
        return []
    if mode == "sequential":
        cap = max(1, cfg.max_sequential_handoffs)
        return routes[:cap]
    if mode == "parallel":
        cap = max(1, cfg.max_parallel_handoffs)
        return routes[:cap]
    return routes[:1]


def build_route_plan(
    mode: RouteMode,
    routes: list[AgentRoute],
    *,
    source: str,
    limits: RouteLimits | None = None,
) -> AgentRoutePlan:
    """构建最终路由计划；空 routes 抛出 ValueError。"""
    capped = cap_routes(mode, routes, limits=limits)
    if not capped:
        raise ValueError("routes must not be empty")
    effective_mode: RouteMode = mode if len(capped) > 1 else "single"
    return AgentRoutePlan(mode=effective_mode, routes=tuple(capped), source=source)
