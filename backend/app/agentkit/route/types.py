"""智能体路由与编排 — 共享类型（零 I/O 依赖）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RouteMode = Literal["single", "sequential", "parallel"]

# 默认路由原因文案；宿主可扩展或覆盖
ROUTE_REASONS: dict[str, str] = {
    "research": "资料检索 / 知识问答",
    "report": "撰写报告 / 长文档",
    "orchestrator": "日常交流 / 兜底调度",
}

FALLBACK_AGENT_ID = "orchestrator"


@dataclass(frozen=True, slots=True)
class AgentRoute:
    """单条路由：目标 agent_id + 人类可读原因。"""

    agent_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AgentRoutePlan:
    """路由计划：模式 + 有序路由列表 + 可选能力缺口元数据。"""

    mode: RouteMode
    routes: tuple[AgentRoute, ...]
    source: str = "skill"
    missing_skill_tags: tuple[str, ...] = ()
    feasible_goal: str = ""
    unsupported_part: str = ""
    capability_gap_instruction: str = ""
    missing_capability_receipt: dict[str, Any] | None = None
