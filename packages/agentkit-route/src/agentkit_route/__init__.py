"""agentkit-route — 多智能体路由类型与纯逻辑。

本包只包含 **数据类型** 与 **不依赖 I/O/I18n 的路由算法**；
语言/平台相关的意图检测由宿主通过 ``SignalDetector`` Protocol 注入。
"""

__version__ = "4.6.0"

from agentkit_route.routing import (
    RouteLimits,
    build_route_plan,
    cap_routes,
    infer_route_mode,
    pick_route_with_fallback,
)
from agentkit_route.scoring import filter_routes_by_agent_scores
from agentkit_route.signals import CompoundDetector, SignalDetector, never_detected
from agentkit_route.types import (
    FALLBACK_AGENT_ID,
    ROUTE_REASONS,
    AgentRoute,
    AgentRoutePlan,
    RouteMode,
)

__all__ = [
    "AgentRoute",
    "AgentRoutePlan",
    "CompoundDetector",
    "FALLBACK_AGENT_ID",
    "ROUTE_REASONS",
    "RouteLimits",
    "RouteMode",
    "SignalDetector",
    "build_route_plan",
    "cap_routes",
    "filter_routes_by_agent_scores",
    "infer_route_mode",
    "never_detected",
    "pick_route_with_fallback",
]
