"""agentkit-orchestrate — 多专精任务编排引擎（Protocol 注入，无 DB/LLM）。"""

__version__ = "4.6.0"

from app.agentkit.orchestrate.assist import AssistRules, resolve_assist_agent_id, should_escalate_to_skill_dev
from app.agentkit.orchestrate.assessment import (
    OrchestratorAnswerAssessment,
    assess_answer_coverage_rule,
    build_deliverable_brief,
    build_global_round_reflection,
)
from app.agentkit.orchestrate.document import extract_document_contexts_from_results
from app.agentkit.orchestrate.events import workflow_plan_tasks, workflow_task_event
from app.agentkit.orchestrate.event_parse import (
    successful_tool_summaries_in_events,
    tool_failed_in_events,
    tool_failure_lines_in_events,
)
from app.agentkit.orchestrate.ids import new_plan_step_id, new_task_step_id
from app.agentkit.orchestrate.messages import (
    build_assist_resume_message,
    build_helper_assist_message,
    build_orchestrator_corrected_retry_message,
    build_retry_user_message,
    build_skill_dev_escalation_message,
)
from app.agentkit.orchestrate.parallel import iter_parallel_task_events, iter_task_event_parts
from app.agentkit.orchestrate.tasks import tasks_from_routes
from app.agentkit.orchestrate.types import (
    ORCH_TASK_RESULT,
    OrchestratorTask,
    TaskExecutionResult,
)
from app.agentkit.orchestrate.verify import VerifyHooks, VerifyRules, verify_task_result

__all__ = [
    "ORCH_TASK_RESULT",
    "AssistRules",
    "OrchestratorAnswerAssessment",
    "OrchestratorTask",
    "TaskExecutionResult",
    "VerifyHooks",
    "VerifyRules",
    "assess_answer_coverage_rule",
    "build_assist_resume_message",
    "build_deliverable_brief",
    "build_global_round_reflection",
    "build_helper_assist_message",
    "build_orchestrator_corrected_retry_message",
    "build_retry_user_message",
    "build_skill_dev_escalation_message",
    "extract_document_contexts_from_results",
    "iter_parallel_task_events",
    "iter_task_event_parts",
    "new_plan_step_id",
    "new_task_step_id",
    "resolve_assist_agent_id",
    "should_escalate_to_skill_dev",
    "successful_tool_summaries_in_events",
    "tasks_from_routes",
    "tool_failed_in_events",
    "tool_failure_lines_in_events",
    "verify_task_result",
    "workflow_plan_tasks",
    "workflow_task_event",
]
