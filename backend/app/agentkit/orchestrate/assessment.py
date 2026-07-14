"""调度层用户诉求验收 — 规则层。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.agentkit.orchestrate.document import extract_document_contexts_from_results
from app.agentkit.orchestrate.types import TaskExecutionResult


def _reply_text(complete: dict[str, Any] | None) -> str:
    """提取 complete 的回复文本（惰性导入 AIP）。"""
    if not complete:
        return ""
    from app.agentkit.aip.messaging import reply_text_from_complete

    return reply_text_from_complete(complete).strip()


@dataclass
class OrchestratorAnswerAssessment:
    """子任务结果是否已回应用户原始诉求。"""

    addresses_user: bool
    reason: str = ""
    gap: str = ""


def build_deliverable_brief(results: list[TaskExecutionResult]) -> str:
    lines: list[str] = []
    for item in results:
        task = item.task
        status = "完成" if item.satisfied else "未完成"
        summary = (task.summary or "").strip()
        if not summary and item.complete:
            summary = _reply_text(item.complete)[:600]
        if not summary and not item.satisfied:
            summary = (task.last_error or "（无摘要）").strip()
        lines.append(f"- [{status}] {task.title}：{summary or '（无摘要）'}")
    return "\n".join(lines)


def assess_answer_coverage_rule(
    user_message: str,
    results: list[TaskExecutionResult],
    *,
    is_substantive_deliverable: Callable[[str], bool],
) -> OrchestratorAnswerAssessment:
    if not (user_message or "").strip():
        return OrchestratorAnswerAssessment(True, reason="无用户诉求")

    if not results:
        return OrchestratorAnswerAssessment(
            False,
            reason="无子任务结果",
            gap="未产生可汇总的子任务交付",
        )

    satisfied = [item for item in results if item.satisfied]
    if not satisfied:
        err_parts = [
            f"{item.task.title}：{(item.task.last_error or '未完成').strip()}"
            for item in results
        ]
        return OrchestratorAnswerAssessment(
            False,
            reason="子任务均未验收通过",
            gap="；".join(err_parts)[:400],
        )

    has_substantive = False
    for item in satisfied:
        summary = (item.task.summary or "").strip()
        if not summary and item.complete:
            summary = _reply_text(item.complete)
        if is_substantive_deliverable(summary):
            has_substantive = True
            break

    if not has_substantive:
        doc_contexts = extract_document_contexts_from_results(results)
        has_doc = any(str(ctx.get("full_text") or "").strip() for ctx in doc_contexts)
        gap = (
            "已有文档正文证据，但尚未形成对用户问题的回答"
            if has_doc
            else "子任务交付仅为工具状态或空摘要，缺少面向用户的回答"
        )
        return OrchestratorAnswerAssessment(False, reason="缺少实质交付物", gap=gap)

    return OrchestratorAnswerAssessment(
        True,
        reason="规则层：存在实质子任务交付，待语义验收",
    )


def build_global_round_reflection(
    *,
    global_round: int,
    assessment: OrchestratorAnswerAssessment,
    results: list[TaskExecutionResult],
    routing_context_line: str = "",
) -> str:
    from app.agentkit.orchestrate.event_parse import tool_failure_lines_in_events

    gap = (assessment.gap or assessment.reason or "验收未通过").strip()
    brief = build_deliverable_brief(results)
    failed_agents = list(
        dict.fromkeys(
            item.task.agent_id for item in results if not item.satisfied and item.task.agent_id
        )
    )
    parts = [f"第 {global_round + 1} 轮全局验收未通过：{gap}"]
    if brief.strip():
        parts.append(f"子任务摘要：\n{brief}")
    ctx_line = routing_context_line
    if not ctx_line and failed_agents:
        ctx_line = f"涉及专精：{', '.join(failed_agents)}"
    if ctx_line:
        parts.append(ctx_line)
    corrections: list[str] = []
    for item in results:
        if item.satisfied:
            continue
        corr = (item.task.correction_instruction or "").strip()
        if corr:
            corrections.append(f"- {item.task.title}：{corr[:500]}")
    if corrections:
        parts.append("调度改正指引：\n" + "\n".join(corrections))
    # ── 提取具体工具失败详情（避免重复无效路径） ──
    tool_failures: list[str] = []
    for item in results:
        if item.satisfied:
            continue
        failures = tool_failure_lines_in_events(item.events)
        for f in failures:
            desc = f"{item.task.title} / {f}" if item.task.title else f
            if desc not in tool_failures:
                tool_failures.append(desc)
    if tool_failures:
        parts.append("工具失败详情：\n" + "\n".join(f"- {tf[:300]}" for tf in tool_failures))
    return "\n".join(parts).strip()
