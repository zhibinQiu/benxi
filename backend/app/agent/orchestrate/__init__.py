"""app.agent.orchestrate — 多专精任务编排引擎（Protocol 注入，无 DB/LLM）。"""

from app.agent import __version__  # noqa: F401

from app.agent.orchestrate.assist import AssistRules, resolve_assist_agent_id, should_escalate_to_skill_dev
from app.agent.orchestrate.assessment import (
    OrchestratorAnswerAssessment,
    assess_answer_coverage_rule,
    build_deliverable_brief,
    build_global_round_reflection,
)
from app.agent.orchestrate.document import extract_document_contexts_from_results
from app.agent.orchestrate.events import workflow_plan_tasks, workflow_task_event
from app.agent.orchestrate.protocol import (
    STAGE_EXECUTING,
    STAGE_PLANNING,
    STAGE_THINKING,
    enrich_workflow_data,
    format_reasoning_line,
    resolve_stage,
)
from app.agent.orchestrate.event_parse import (
    successful_tool_summaries_in_events,
    tool_failed_in_events,
    tool_failure_lines_in_events,
)
from app.agent.orchestrate.ids import new_plan_step_id, new_task_step_id
from app.agent.orchestrate.messages import (
    build_assist_resume_message,
    build_helper_assist_message,
    build_orchestrator_corrected_retry_message,
    build_retry_user_message,
    build_skill_dev_escalation_message,
)
from app.agent.orchestrate.dag import TaskDAG, TaskNode, build_task_dag
from app.agent.orchestrate.parallel import iter_parallel_task_events, iter_task_event_parts
from app.agent.orchestrate.scheduler import iter_dag_wave_events
from app.agent.orchestrate.tasks import tasks_from_routes
from app.agent.orchestrate.types import (
    ORCH_TASK_RESULT,
    OrchestratorTask,
    TaskExecutionResult,
)
from app.agent.orchestrate.verify import VerifyHooks, VerifyRules, verify_task_result

__all__ = [
    "ORCH_TASK_RESULT",
    "AssistRules",
    "OrchestratorAnswerAssessment",
    "OrchestratorTask",
    "STAGE_EXECUTING",
    "STAGE_PLANNING",
    "STAGE_THINKING",
    "TaskDAG",
    "TaskExecutionResult",
    "TaskNode",
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
    "build_task_dag",
    "enrich_workflow_data",
    "extract_document_contexts_from_results",
    "format_reasoning_line",
    "iter_dag_wave_events",
    "iter_parallel_task_events",
    "iter_task_event_parts",
    "new_plan_step_id",
    "new_task_step_id",
    "resolve_assist_agent_id",
    "resolve_stage",
    "should_escalate_to_skill_dev",
    "successful_tool_summaries_in_events",
    "tasks_from_routes",
    "tool_failed_in_events",
    "tool_failure_lines_in_events",
    "verify_task_result",
    "workflow_plan_tasks",
    "workflow_task_event",
]
