"""任务验收 — 规则层（交付物 / 工具证据）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.agentkit.orchestrate.event_parse import successful_tool_summaries_in_events, tool_failed_in_events
from app.agentkit.orchestrate.types import OrchestratorTask


def _reply_from_complete(complete: dict | None) -> str:
    """从 complete 提取 reply 文本（惰性导入 AIP）。"""
    if not complete:
        return ""
    from app.agentkit.aip.messaging import reply_text_from_complete

    return reply_text_from_complete(complete).strip()


@dataclass(frozen=True, slots=True)
class VerifyRules:
    """宿主注入的业务 agent 分类与 marker 文案。"""

    action_agent_ids: frozenset[str] = frozenset()
    skill_dev_agent_id: str = "skill-dev"
    skill_outcome_markers: tuple[str, ...] = ()
    deliverable_retry_hint: str = (
        "请基于工具证据写出可交给调度层的子任务交付摘要，直接回应子任务诉求；"
        "勿仅复述工具状态或读取字数。"
    )


@dataclass(frozen=True, slots=True)
class VerifyHooks:
    """宿主注入的交付物判定（通常来自 reply_synth）。"""

    is_substantive_deliverable: Callable[[str], bool]
    reply_looks_like_denial: Callable[[str], bool]
    is_internal_tool_line: Callable[[str], bool] = field(default=lambda _t: False)
    action_retry_hint: Callable[[str], str] = field(
        default=lambda agent_id: "请调用已分配工具完成该步骤。"
    )


def _summary_from_reply(reply: str) -> str:
    summary = reply.split("\n", 1)[0].strip()[:160]
    if len(summary) < 8 and len(reply) > 8:
        summary = reply[:160]
    return summary


def _skill_outcome_in_summaries(
    tool_summaries: list[str],
    markers: tuple[str, ...],
) -> bool:
    return any(any(marker in summary for marker in markers) for summary in tool_summaries)


def verify_task_result(
    task: OrchestratorTask,
    events: list[dict],
    complete: dict | None,
    *,
    rules: VerifyRules,
    hooks: VerifyHooks,
) -> tuple[bool, str, str]:
    """规则验收：须有实质交付物；工具成功仅作证据。"""
    failed, fail_detail = tool_failed_in_events(events)
    if failed:
        return (
            False,
            "",
            f"请修正后重试：{fail_detail}" if fail_detail else "上次工具调用失败，请换用正确工具重试",
        )

    reply = _reply_from_complete(complete)
    citations = list((complete or {}).get("citations") or [])
    tool_summaries = successful_tool_summaries_in_events(
        events,
        is_internal_line=hooks.is_internal_tool_line,
    )
    agent_id = (task.agent_id or "").strip()

    if agent_id in rules.action_agent_ids and not tool_summaries:
        if not reply or hooks.reply_looks_like_denial(reply):
            return False, "", hooks.action_retry_hint(agent_id)
        return False, "", "请调用平台工具完成该步骤，勿仅口头说明已完成"

    if agent_id == rules.skill_dev_agent_id and not _skill_outcome_in_summaries(
        tool_summaries, rules.skill_outcome_markers
    ):
        if not reply or hooks.reply_looks_like_denial(reply):
            return False, "", hooks.action_retry_hint(agent_id)
        if not tool_summaries:
            return False, "", hooks.action_retry_hint(agent_id)

    if agent_id in rules.action_agent_ids and tool_summaries and not hooks.is_substantive_deliverable(reply):
        return False, "", rules.deliverable_retry_hint

    if hooks.is_substantive_deliverable(reply):
        if agent_id in rules.action_agent_ids and not tool_summaries:
            return False, "", hooks.action_retry_hint(agent_id)
        return True, _summary_from_reply(reply), ""

    if tool_summaries and not reply:
        return False, "", rules.deliverable_retry_hint

    if reply and not hooks.reply_looks_like_denial(reply):
        if citations or agent_id not in rules.action_agent_ids:
            if hooks.is_substantive_deliverable(reply):
                return True, _summary_from_reply(reply), ""

    if not reply:
        return False, "", "请调用平台工具完成该步骤，勿仅口头说明无法操作"

    if hooks.reply_looks_like_denial(reply) and not citations:
        hint = hooks.action_retry_hint(agent_id)
        if agent_id in rules.action_agent_ids:
            hint = (
                f"{hint} 若平台原子工具确实无法满足，"
                "请说明缺口并由调度层转 skill-dev 创建能力。"
            )
        return False, "", hint

    return True, _summary_from_reply(reply), ""
