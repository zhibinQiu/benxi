"""路由 → 任务清单。"""

from __future__ import annotations

from collections.abc import Callable

from app.agentkit.route.types import AgentRoute
from app.agentkit.orchestrate.types import OrchestratorTask


def tasks_from_routes(
    routes: list[AgentRoute],
    *,
    title_fn: Callable[[str], str] | None = None,
) -> list[OrchestratorTask]:
    """将路由列表转为最小任务清单（一条路由一项）。"""
    resolve_title = title_fn or (lambda agent_id: agent_id)
    return [
        OrchestratorTask(
            id=f"t{idx}",
            title=resolve_title(r.agent_id),
            agent_id=r.agent_id,
            reason=r.reason,
        )
        for idx, r in enumerate(routes, start=1)
    ]


def routes_to_refs(routes: list[AgentRoute]) -> list[AgentRoute]:
    """向后兼容：RouteRef 已合并至 AgentRoute，直接返回。"""
    return list(routes)
