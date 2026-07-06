"""Agent 执行规划类型 — 规划器输出的核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentToolPlan:
    """Agent 工具规划：附件使用、意图标签与上下文指令。"""

    use_attachment: bool
    intent_label: str
    context_instruction: str


@dataclass(frozen=True, slots=True)
class AgentExecutionPlan:
    """Agent 执行规划：区分原子工具调用与发展技能。"""

    reasoning: str
    intent: str
    direct_answer: bool
    atomic_tools: tuple[str, ...]
    skip_tools: tuple[str, ...]
    uploaded_skill: str | None
    builtin_orchestration: str | None
    steps: tuple[str, ...]
    source: str
    metadata: dict[str, Any] | None = None


__all__ = [
    "AgentExecutionPlan",
    "AgentToolPlan",
]
