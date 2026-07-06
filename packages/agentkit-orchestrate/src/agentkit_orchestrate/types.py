"""编排领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentkit_route.types import AgentRoute

ORCH_TASK_RESULT = "_orchestrator_task_result"
ORCH_ROUND_RESULT = "_orchestrator_round_result"
ORCH_ASSESSMENT_RESULT = "_orchestrator_assessment_result"


@dataclass
class OrchestratorTask:
    id: str
    title: str
    agent_id: str
    reason: str
    status: str = "pending"
    summary: str = ""
    attempts: int = 0
    last_error: str = ""
    correction_instruction: str = ""


@dataclass
class TaskExecutionResult:
    """子任务执行结果。``aip_handoff`` 由宿主注入 AIP 消息（可选）。"""

    task: OrchestratorTask
    route: AgentRoute | Any
    events: list[dict[str, Any]] = field(default_factory=list)
    complete: dict[str, Any] | None = None
    satisfied: bool = False
    aip_handoff: Any | None = None
