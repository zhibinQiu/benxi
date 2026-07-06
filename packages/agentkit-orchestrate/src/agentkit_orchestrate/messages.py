"""编排消息模板 — 重试 / 协助 / skill-dev 升级。"""

from __future__ import annotations

from typing import Any

from agentkit_orchestrate.types import OrchestratorTask


def build_retry_user_message(
    original: str,
    task: OrchestratorTask,
    retry_hint: str,
) -> str:
    return f"{original.strip()}\n\n【重试 · {task.title}】{retry_hint.strip()}"


def build_orchestrator_corrected_retry_message(
    original: str,
    task: OrchestratorTask,
    correction: str,
) -> str:
    """调度层生成的具体改正说明，交给专精智能体重试。"""
    text = (correction or task.last_error or "").strip()
    return (
        f"{original.strip()}\n\n"
        f"【调度改正 · {task.title}】\n"
        f"{text}\n\n"
        "请严格按上述改正说明执行，勿重复已失败的工具调用方式。"
    )


def build_helper_assist_message(
    user_message: str,
    parent_task: OrchestratorTask,
    assist: dict[str, Any],
) -> str:
    reason = str(assist.get("reason") or "").strip()
    needed = str(assist.get("needed_from") or "").strip()
    partial = str(assist.get("partial_progress") or "").strip()
    lines = [
        user_message.strip(),
        f"【调度协调 · 协助 {parent_task.title}】",
        f"请求方反馈：{reason}",
    ]
    if needed:
        lines.append(f"需要协助：{needed}")
    if partial:
        lines.append(f"请求方已有进展：{partial[:400]}")
    lines.append(
        "请在本专精域内自主完成上述协助子任务；"
        "给出可验收结论供调度层交还原请求方续办，勿写面向最终用户的完整答覆。"
    )
    return "\n".join(line for line in lines if line.strip())


def build_assist_resume_message(
    *,
    session_id: str,
    task_id: str,
    target_agent_id: str,
    user_message: str,
    helper_title: str,
    helper_summary: str,
    session_bus: Any = None,
) -> str:
    from agentkit_aip import get_session_bus

    bus = session_bus or get_session_bus()
    base = bus.format_task_request_for_llm(
        session_id=session_id,
        task_id=task_id,
        target_agent_id=target_agent_id,
        user_message=user_message,
    )
    summary = (helper_summary or "").strip()[:800]
    return (
        f"{base}\n\n"
        f"【调度协调 · 续办】协助方 {helper_title} 已完成"
        + (f"：{summary}" if summary else "")
        + "\n请结合上述协助结果继续完成你负责的步骤。"
    )


def build_skill_dev_escalation_message(
    user_message: str,
    task: OrchestratorTask,
) -> str:
    err = (task.last_error or "未能完成").strip()
    return (
        f"{user_message.strip()}\n\n"
        f"【调度补能力 · {task.title}】上一专精步骤未满足用户诉求（{err}）。"
        "请先 invoke_context_subagent 完成网页/公开信息调研；"
        "再 invoke_skill(skill-development, call, {operation: create_skill, ...})"
        "并 run_skill_script 验证。"
    )
