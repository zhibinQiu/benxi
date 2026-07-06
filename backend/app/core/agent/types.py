"""智能体路由与编排 — 类型定义（agentkit-route + 平台路由文案）。"""

from __future__ import annotations

from agentkit_route.types import AgentRoute, AgentRoutePlan, RouteMode

FALLBACK_AGENT_ID = "orchestrator"

ROUTE_REASONS: dict[str, str] = {
    "platform": "平台信息 / 待办 / 系统数据",
    "scheduler": "时间调度 / 延迟提醒",
    "rpa": "浏览器自动化 / 网页交互",
    "skill-dev": "Skill 创建/更新/执行",
    "orchestrator": "通用交流",
}

__all__ = [
    "FALLBACK_AGENT_ID",
    "ROUTE_REASONS",
    "AgentRoute",
    "AgentRoutePlan",
    "RouteMode",
]
