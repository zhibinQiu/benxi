"""父智能体任务编排 — Platform 薄适配（规则配置 + 平台专属能力）。"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.agentkit.aip.types import AipMessage
from app.agentkit.orchestrate import (
    AssistRules,
    OrchestratorAnswerAssessment,
    OrchestratorTask,
    TaskExecutionResult,
    VerifyHooks,
    VerifyRules,
    assess_answer_coverage_rule,
    build_assist_resume_message as _build_assist_resume_message,
    build_deliverable_brief,
    build_global_round_reflection as _build_global_round_reflection,
    build_helper_assist_message,
    build_orchestrator_corrected_retry_message,
    build_retry_user_message,
    build_skill_dev_escalation_message,
    extract_document_contexts_from_results,
    new_plan_step_id,
    new_task_step_id,
    resolve_assist_agent_id as _resolve_assist_agent_id,
    should_escalate_to_skill_dev as _should_escalate_to_skill_dev,
    tasks_from_routes as _tasks_from_routes,
    tool_failure_lines_in_events,
    verify_task_result as _verify_task_result,
    workflow_plan_tasks as _workflow_plan_tasks,
    workflow_task_event as _workflow_task_event,
)

from app.core.agent_profiles import get_agent_profile, resolve_agent_title
from app.services.agent_skill_routing import format_routing_context_line

_logger = logging.getLogger(__name__)

# 最大子任务尝试次数（内部使用，非导出）

# 平台 agent 分类与 marker（注入 agentkit-orchestrate 规则层）
_VERIFY_RULES = VerifyRules(
    action_agent_ids=frozenset({"platform", "rpa"}),
    skill_dev_agent_id="skill-dev",
    skill_outcome_markers=(
        "运行 Skill 脚本",
        "自动执行 Skill",
        "执行含脚本",
        "已创建 Skill",
        "Skill 已创建",
        "创建 Skill：",
        "已更新",
    ),
)
_ASSIST_RULES = AssistRules(
    assistable_agent_ids=frozenset(
        {"platform", "rpa", "skill-dev"}
    ),
    skill_dev_agent_id="skill-dev",
    no_escalate_agent_ids=frozenset({"skill-dev", "orchestrator"}),
    skill_escalation_markers=(
        "create_skill",
        "run_skill_script",
        "list_agent_skills",
        "发展技能",
        "创建 Skill",
        "平台缺能力",
        "请勿推脱",
        "无直接创建",
        "无查询接口",
        "无定时提醒",
        "请调用平台工具",
    ),
    action_agent_ids=frozenset({"platform", "rpa"}),
)


_RETRY_HINTS: dict[str, str] = {
    "skill-dev": (
        "Skill 包管理：invoke_skill(skill-development, call, {operation, ...})；"
        "operation 用 list_agent_skills（勿 list_uploaded_skills）。"
        "浏览器调研（创建抓取类 Skill 的中间步骤）：直接 invoke_skill(browser-automation, call, ...)。"
        "纯主题检索调研：invoke_context_subagent(kind=explore, queries=[...])。"
        "禁止仅口头说明无法完成。"
    ),
}
_DEFAULT_RETRY_HINT = (
    "请调用已分配的平台工具完成操作；若确实无匹配工具，"
    "说明已尝试的工具名，勿推脱让用户手动处理。"
)

_VERIFY_HOOKS_CACHE: VerifyHooks | None = None


def _action_retry_hint(agent_id: str) -> str:
    return _RETRY_HINTS.get(agent_id, _DEFAULT_RETRY_HINT)


def _verify_hooks() -> VerifyHooks:
    global _VERIFY_HOOKS_CACHE
    if _VERIFY_HOOKS_CACHE is None:
        from app.services.agent_reply_synth import (
            is_internal_tool_outcome_line,
            is_substantive_deliverable,
            reply_looks_like_denial,
        )
        _VERIFY_HOOKS_CACHE = VerifyHooks(
            is_substantive_deliverable=is_substantive_deliverable,
            reply_looks_like_denial=reply_looks_like_denial,
            is_internal_tool_line=is_internal_tool_outcome_line,
            action_retry_hint=_action_retry_hint,
        )
    return _VERIFY_HOOKS_CACHE


def tasks_from_routes(routes: list[Any]) -> list[OrchestratorTask]:
    def _title(agent_id: str) -> str:
        profile = get_agent_profile(agent_id)
        return profile.title if profile else agent_id

    return _tasks_from_routes(routes, title_fn=_title)


def workflow_plan_tasks(
    tasks: list[OrchestratorTask],
    *,
    step_id: str,
    mode: str = "sequential",
) -> dict[str, Any]:
    return _workflow_plan_tasks(
        tasks,
        step_id=step_id,
        mode=mode,
        orchestrator_title="orchestrator",
        orchestrator_label=resolve_agent_title("orchestrator"),
    )


def workflow_task_event(
    phase: str,
    task: OrchestratorTask,
    *,
    step_id: str,
    detail: str = "",
    attempt: int | None = None,
    all_tasks: list[OrchestratorTask] | None = None,
) -> dict[str, Any]:
    return _workflow_task_event(
        phase,
        task,
        step_id=step_id,
        detail=detail,
        attempt=attempt,
        all_tasks=all_tasks,
        agent_title_fn=resolve_agent_title,
    )


def verify_task_result(
    task: OrchestratorTask,
    events: list[dict[str, Any]],
    complete: dict[str, Any] | None,
) -> tuple[bool, str, str]:
    return _verify_task_result(
        task, events, complete, rules=_VERIFY_RULES, hooks=_verify_hooks()
    )


def should_escalate_to_skill_dev(
    task: OrchestratorTask,
    *,
    satisfied: bool,
    events: list[dict[str, Any]],
) -> bool:
    from app.services.agent_reply_synth import is_internal_tool_outcome_line

    return _should_escalate_to_skill_dev(
        task,
        satisfied=satisfied,
        events=events,
        rules=_ASSIST_RULES,
        is_internal_tool_line=is_internal_tool_outcome_line,
    )


def resolve_assist_agent_id(
    assist: dict[str, Any] | None,
    task: OrchestratorTask,
    user_message: str,
    *,
    events: list[dict[str, Any]] | None = None,
) -> str | None:
    from app.services.agent_reply_synth import is_internal_tool_outcome_line

    def _escalate(t: OrchestratorTask, **kw: Any) -> bool:
        return _should_escalate_to_skill_dev(
            t,
            rules=_ASSIST_RULES,
            is_internal_tool_line=is_internal_tool_outcome_line,
            **kw,
        )

    return _resolve_assist_agent_id(
        assist,
        task,
        user_message,
        rules=_ASSIST_RULES,
        events=events,
        should_escalate_fn=_escalate,
    )


def build_assist_resume_message(
    *,
    session_id: str,
    task_id: str,
    target_agent_id: str,
    user_message: str,
    helper_title: str,
    helper_summary: str,
) -> str:
    from app.core.aip.session_bus import get_session_bus

    return _build_assist_resume_message(
        session_id=session_id,
        task_id=task_id,
        target_agent_id=target_agent_id,
        user_message=user_message,
        helper_title=helper_title,
        helper_summary=helper_summary,
        bus=get_session_bus(),
    )


def assess_orchestrator_answer_coverage_rule(
    user_message: str,
    results: list[TaskExecutionResult],
) -> OrchestratorAnswerAssessment:
    from app.services.agent_reply_synth import is_substantive_deliverable

    return assess_answer_coverage_rule(
        user_message,
        results,
        is_substantive_deliverable=is_substantive_deliverable,
    )


build_deliverable_brief_for_assessment = build_deliverable_brief


def build_global_round_reflection(
    *,
    global_round: int,
    assessment: OrchestratorAnswerAssessment,
    results: list[TaskExecutionResult],
) -> str:
    failed_agents = list(
        dict.fromkeys(
            item.task.agent_id for item in results if not item.satisfied and item.task.agent_id
        )
    )
    ctx_line = format_routing_context_line(failed_agents)
    return _build_global_round_reflection(
        global_round=global_round,
        assessment=assessment,
        results=results,
        routing_context_line=ctx_line,
    )


# --- 平台专属：浏览器截图 URL / 用户记忆 ---

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_PLAIN_SCREENSHOT_URL_RE = re.compile(
    r"(?:/ai)?/api/v1/browser-rpa/screenshot\?key=[^\s<>\"')\]]+"
)


def extract_image_attachments_from_markdown(
    reply: str | None,
) -> list[dict[str, Any]]:
    """从回复 Markdown 或裸 URL 中解析浏览器截图附件。"""
    text = str(reply or "")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _append(url: str, title: str = "浏览器截图") -> None:
        clean = url.strip()
        if not clean or "/browser-rpa/screenshot" not in clean or clean in seen:
            return
        seen.add(clean)
        out.append({"type": "image", "url": clean, "title": title or "浏览器截图"})

    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        title = (match.group(1) or "浏览器截图").strip() or "浏览器截图"
        _append(match.group(2) or "", title)
    for match in _PLAIN_SCREENSHOT_URL_RE.finditer(text):
        _append(match.group(0) or "")
    return out


def collect_image_attachments_from_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "attachment":
            continue
        data = event.get("data") or {}
        if data.get("type") != "image":
            continue
        url = str(data.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(dict(data))
    return out


def collect_screenshot_attachments_from_task_results(
    results: list[Any],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in results:
        for att in collect_image_attachments_from_events(item.events):
            url = str(att.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(att)
        complete = item.complete or {}
        for att in extract_image_attachments_from_markdown(str(complete.get("reply") or "")):
            url = str(att.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(att)
    return out


def append_screenshot_markdown_to_reply(
    reply: str | None,
    attachments: list[dict[str, Any]],
) -> str | None:
    if not attachments:
        return reply
    parts: list[str] = []
    base = (reply or "").strip()
    if base:
        parts.append(base)
    image_blocks: list[str] = []
    for att in attachments:
        url = str(att.get("url") or "").strip()
        if not url or url in base:
            continue
        title = str(att.get("title") or "浏览器截图").strip() or "浏览器截图"
        image_blocks.append(f"![{title}]({url})")
    if not image_blocks:
        return reply if not parts else "\n\n".join(parts).strip()
    if base and "页面截图" not in base:
        parts.append("### 页面截图")
    parts.extend(image_blocks)
    merged = "\n\n".join(parts).strip()
    return merged or None


def build_task_plan_workflow_update(tasks: list[OrchestratorTask]) -> list[dict[str, Any]]:
    from app.agentkit.orchestrate.events import task_to_json

    return [task_to_json(t) for t in tasks]


def _fallback_specialist_correction(
    *,
    task: OrchestratorTask,
    rule_hint: str,
    failures: list[str],
    specialist_reply: str,
) -> str:
    parts: list[str] = []
    if rule_hint.strip():
        parts.append(rule_hint.strip())
    if failures:
        parts.append("失败工具：" + "；".join(failures[:6]))
    if specialist_reply.strip():
        parts.append(f"专精回复摘要：{specialist_reply.strip()[:300]}")
    if task.agent_id == "skill-dev":
        parts.append(
            "主业：invoke_skill(skill-development, call, {operation, ...})，"
            "operation 用 list_agent_skills（勿 list_uploaded_skills）。"
            "浏览器调研（创建抓取 Skill 中间步骤）：直接 invoke_skill(browser-automation, call, ...)。"
            "主题检索调研：invoke_context_subagent(kind=explore, queries=[...])。"
        )
    return "\n".join(parts) if parts else "请换用正确工具与参数重试，勿重复失败路径。"


async def synthesize_specialist_correction_instruction(
    *,
    user_message: str,
    task: OrchestratorTask,
    events: list[dict[str, Any]],
    complete: dict[str, Any] | None,
    rule_hint: str = "",
    memory_context: str = "",
) -> str:
    """专精多轮失败后，由调度层生成面向专精的具体改正指引（非用户终稿）。"""
    from app.agentkit.aip.messaging import reply_text_from_complete
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    failures = tool_failure_lines_in_events(events)
    specialist_reply = reply_text_from_complete(complete)
    fallback = _fallback_specialist_correction(
        task=task,
        rule_hint=rule_hint,
        failures=failures,
        specialist_reply=specialist_reply,
    )
    if not is_configured():
        return fallback

    profile = get_agent_profile(task.agent_id)
    agent_title = profile.title if profile else task.agent_id
    failure_block = "\n".join(f"- {line}" for line in failures[:8]) or "（无工具失败记录）"

    try:
        choice = await chat_completion_message_async(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是企业助手调度层的执行督导。专精智能体未完成子任务，"
                        "请写出**给该专精智能体**的下一次执行改正说明（简体中文）。\n"
                        "要求：\n"
                        "- 针对失败工具/参数/路径给出可执行改正（工具名、参数结构、应换用的 Skill）\n"
                        "- 禁止面向最终用户的寒暄或完整答覆\n"
                        "- 禁止让用户自行操作\n"
                        "- 若属参数格式错误，写明正确 JSON 字段结构\n"
                        "- 控制在 120–400 字"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        (f"{memory_context.strip()}\n\n" if memory_context.strip() else "")
                        + f"用户原始诉求：{user_message.strip()[:600]}\n"
                        f"子任务：{task.title}（专精 {agent_title} / {task.agent_id}）\n"
                        f"规则验收提示：{rule_hint.strip() or '无'}\n"
                        f"工具失败记录：\n{failure_block}\n"
                        f"专精当前回复摘要：{specialist_reply.strip()[:400] or '（无）'}"
                    ),
                },
            ],
            tools=None,
            temperature=0.2,
            timeout=35.0,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        if content and len(content) >= 24:
            return content[:1200]
    except Exception:
        _logger.exception("调度改正指引生成失败 agent=%s", task.agent_id)
    return fallback


# 兼容旧 import（TaskExecutionResult.aip_handoff 类型注解）
__all__ = [
    "OrchestratorTask",
    "TaskExecutionResult",
    "append_screenshot_markdown_to_reply",
    "extract_image_attachments_from_markdown",
]
