"""路由分数过滤 — 防止多专精低分噪声 handoff。"""

from __future__ import annotations

from agentkit_route.types import AgentRoute


def filter_routes_by_agent_scores(
    routes: list[AgentRoute],
    scores_by_agent_id: dict[str, float],
    *,
    top_score: float,
    floor_ratio: float = 0.3,
    min_floor: float = 1.0,
    max_routes: int = 4,
) -> list[AgentRoute]:
    """按相对分数阈值过滤路由列表。

    当仅一条路由或过滤后为空时，回退为 ``routes[:1]``。
    """
    if len(routes) <= 1:
        return routes
    floor = max(min_floor, top_score * floor_ratio)
    filtered = [r for r in routes if scores_by_agent_id.get(r.agent_id, 0) >= floor]
    if len(filtered) > 1:
        return filtered[:max_routes]
    return routes[:1]
