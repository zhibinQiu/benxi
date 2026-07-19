"""调度协助 — 星型编排 agent 选择。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agentkit.orchestrate.event_parse import successful_tool_summaries_in_events
from app.agentkit.orchestrate.types import OrchestratorTask


@dataclass(frozen=True, slots=True)
class AssistRules:
    """协助专精选择规则（宿主配置 agent_id 集合与 keyword 映射）。"""

    assistable_agent_ids: frozenset[str] = frozenset()
    skill_dev_agent_id: str = "skill-dev"
    no_escalate_agent_ids: frozenset[str] = frozenset()
    skill_escalation_markers: tuple[str, ...] = ()
    action_agent_ids: frozenset[str] = frozenset()


def should_escalate_to_skill_dev(
    task: OrchestratorTask,
    *,
    satisfied: bool,
    events: list[dict[str, Any]],
    rules: AssistRules,
    is_internal_tool_line: Any = None,
) -> bool:
    if satisfied or task.agent_id in rules.no_escalate_agent_ids:
        return False
    hint = task.last_error or ""
    if "权限" in hint or "permission" in hint.lower():
        return False
    if any(marker in hint for marker in rules.skill_escalation_markers):
        return True
    internal = is_internal_tool_line or (lambda _t: False)
    summaries = successful_tool_summaries_in_events(events, is_internal_line=internal)
    if task.agent_id in rules.action_agent_ids and not summaries:
        return True
    return False


def resolve_assist_agent_id(
    assist: dict[str, Any] | None,
    task: OrchestratorTask,
    user_message: str,
    *,
    rules: AssistRules,
    events: list[dict[str, Any]] | None = None,
    should_escalate_fn: Any = None,
) -> str | None:
    """根据专精 assist 反馈或验收失败信息选择协助专精。"""
    if assist:
        suggested = str(assist.get("suggested_agent_id") or "").strip()
        if suggested in rules.assistable_agent_ids and suggested != task.agent_id:
            return suggested
        blob = " ".join(
            str(assist.get(k) or "")
            for k in ("needed_from", "reason", "partial_progress")
        ).lower()
        agent = _keyword_to_agent(blob, rules)
        if agent and agent != task.agent_id:
            return agent

    escalate = should_escalate_fn or (
        lambda t, **kw: should_escalate_to_skill_dev(t, rules=rules, **kw)
    )
    if escalate(task, satisfied=False, events=events or []):
        return rules.skill_dev_agent_id
    _ = user_message
    return None


def _keyword_to_agent(blob: str, rules: AssistRules) -> str:
    if any(k in blob for k in ("skill", "脚本", "create_uploaded", "run_skill")):
        return rules.skill_dev_agent_id
    if any(k in blob for k in ("检索", "调研", "知识库", "联网", "政策")):
        return "research"
    if any(k in blob for k in ("文档", "待办", "通知", "用户", "部门", "文件夹")):
        return "platform"
    if any(k in blob for k in ("报告", "方案", "可研")):
        return "report"
    if any(k in blob for k in ("图", "mermaid", "流程图", "思维导图")):
        return "diagram"
    if any(k in blob for k in ("浏览器", "网页", "截图")):
        return "orchestrator"
    if any(k in blob for k in ("定时", "提醒", "schedule")):
        return "orchestrator"
    return ""
