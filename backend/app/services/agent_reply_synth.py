"""工具循环结束后的用户可见回复合成 — 与 tool loop 内 assistant 正文隔离。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.core.agent_loop_state import LoopState

from app.core.agent_message_parse import (
    looks_like_internal_agent_content,
)
from app.core.aip.handoff import SpecialistHandoffResult, build_specialist_handoff_result
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_skill_router import is_skill_management_message

_DENIAL_MARKERS = frozenset({
    "无法完成", "无法设置", "无法定", "不能设置", "没法",
    "没能完成", "无法为您", "无直接创建", "无查询接口",
    "无定时提醒", "建议您手动", "建议使用手机", "手机自带",
    "手机计时器", "闹钟功能", "不具备", "不支持",
    "请联系系统管理员", "抱歉，这次没能",
})

_USER_COMMAND_RE = re.compile(
    r"run_skill_script\s*[\(\'\"]|load_uploaded_skill\s*[\(\'\"]|"
    r"示例命令|请使用示例|建议您运行|建议运行|使用命令|"
    r"args\s*=\s*\[",
    re.I,
)

# 规划/探查类工具摘要 — 仅作证据，不可当作子任务交付物
_INTERNAL_OUTCOME_PREFIXES = (
    "Skills 目录",
    "加载 Skill",
    "搜索工具",
    "请求调度协助",
)

# 工具操作回顾 — 仅描述了工具做了什么，不含实质结果数据
_TOOL_ACTION_REPLAY_PREFIXES = (
    "使用联网搜索查询",
    "使用联网搜索搜索",
    "使用搜索引擎查询",
    "联网检索返回",
    "使用浏览器访问",
    "使用浏览器打开",
    "获取网页内容",
    "读取文档正文",
    "正在搜索",
    "已读取",
    "发起搜索",
    "发起检索",
)

_SKILL_RUN_OUTCOME_MARKERS = (
    "运行 Skill 脚本",
    "自动执行 Skill",
    "执行含脚本",
)

_SKILL_MUTATION_OUTCOME_MARKERS = (
    "已更新",
    "已删除 Skill",
    "已创建 Skill",
    "Skill 已创建",
    "创建 Skill：",
)


def reply_looks_like_denial(text: str) -> bool:
    lowered = (text or "").strip()
    if not lowered:
        return True
    if reply_looks_like_user_command_instruction(lowered):
        return True
    return any(marker in lowered for marker in _DENIAL_MARKERS)


def reply_looks_like_user_command_instruction(text: str) -> bool:
    return bool(_USER_COMMAND_RE.search(text or ""))


def is_internal_tool_outcome_line(line: str) -> bool:
    """仅列目录/加载说明等中间步骤，不算面向用户的任务结果。"""
    text = (line or "").strip()
    if not text:
        return True
    for prefix in _INTERNAL_OUTCOME_PREFIXES:
        if text.startswith(f"{prefix}：") or text.startswith(f"{prefix}:"):
            return True
        if prefix == "请求调度协助" and text.startswith(prefix):
            return True
    return False


def is_tool_action_replay_line(line: str) -> bool:
    """工具操作回顾行——仅描述工具执行了什么操作，不含实质结果数据。"""
    text = (line or "").strip()
    if not text:
        return True
    for prefix in _TOOL_ACTION_REPLAY_PREFIXES:
        if text.startswith(prefix):
            return True
    return False


def looks_like_tool_status_echo(text: str) -> bool:
    """通用：文本是否像工具执行状态复述，而非子任务交付物。"""
    body = (text or "").strip()
    if not body:
        return True
    if body.startswith("读取文档正文"):
        return True
    if "已读取" in body and "正文" in body and re.search(r"\d+\s*字", body):
        return len(body) < 160
    if re.fullmatch(r"共\s*\d+\s*条", body):
        return True
    return False


def is_substantive_deliverable(text: str, *, min_chars: int = 12) -> bool:
    """子任务/用户可见交付物是否具备实质内容（非推脱、非空、非过短状态句）。"""
    body = (text or "").strip()
    if not body or reply_looks_like_denial(body):
        return False
    if looks_like_tool_status_echo(body):
        return False
    return len(body) >= min_chars


def has_deliverable_evidence(loop_state: LoopState | None) -> bool:
    """工具循环是否已积累可合成交付物的证据（与交付物本身区分）。"""
    state = loop_state or {}
    if list(state.get("tool_outcome_lines") or []):
        return True
    if isinstance(state.get("agent_document_context"), dict):
        return bool(str(state["agent_document_context"].get("full_text") or "").strip())
    if list(state.get("retrieval_context_parts") or []):
        return True
    if str(state.get("deterministic_reply") or "").strip():
        return True
    if presentable_skill_conclusion(state):
        return True
    if list(state.get("citations") or []):
        return True
    # 子智能体已回传结论（use/search/execute）也算证据，供父层综合
    if latest_subagent_summary(state):
        return True
    return False


def latest_subagent_summary(loop_state: LoopState | None) -> str:
    """最近一次子智能体回传的摘要（invoke_context_subagent 合并）。"""
    summaries = (loop_state or {}).get("subagent_summaries") or []
    if not summaries:
        return ""
    last = summaries[-1]
    if isinstance(last, dict):
        text = str(last.get("summary") or "").strip()
    else:
        text = str(last or "").strip()
    if not text or text in ("子 Agent 未产出有效摘要",):
        return ""
    return text


def _subagent_summary_is_thin(summary: str) -> bool:
    """execute 步骤路径常只回「tool: 完成」类薄摘要，不足以单独支撑终稿。"""
    import re

    text = (summary or "").strip()
    if not text:
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    status_re = re.compile(
        r"^[\w.\-_/]+:\s*(完成|ok|success|成功|已执行)\s*$",
        re.IGNORECASE,
    )
    return all(
        status_re.match(ln) or ln.lower() in ("完成", "ok", "success", "成功", "已执行")
        for ln in lines
    )


def build_deliverable_evidence_block(loop_state: LoopState | None) -> str:
    """将 loop_state 中的工具/材料证据格式化为合成 prompt 块（非交付物）。"""
    state = loop_state or {}
    parts: list[str] = []

    subagent = latest_subagent_summary(state)
    thin_subagent = bool(subagent) and _subagent_summary_is_thin(subagent)
    if subagent:
        parts.append(f"【子智能体结论（优先引用）】\n{subagent[:6000]}")

    doc_ctx = state.get("agent_document_context")
    if isinstance(doc_ctx, dict):
        title = str(doc_ctx.get("title") or "文档").strip()
        text = str(doc_ctx.get("full_text") or "").strip()
        if text:
            parts.append(f"【文档正文 · {title}】\n{text[:24000]}")

    # 无摘要或摘要过薄时保留检索材料，避免 execute 状态行淹没正文证据
    if not subagent or thin_subagent:
        retrieval = "\n\n".join(
            str(x).strip()
            for x in (state.get("retrieval_context_parts") or [])
            if str(x).strip()
        )
        if retrieval:
            parts.append(f"【检索材料】\n{retrieval[:8000]}")

    det = str(state.get("deterministic_reply") or "").strip()
    if det:
        parts.append(f"【结构化数据】\n{det[:4000]}")

    skill = presentable_skill_conclusion(state)
    if skill:
        parts.append(f"【脚本结论】\n{skill[:4000]}")

    tool_lines = [
        str(x).strip()
        for x in (state.get("tool_outcome_lines") or [])
        if str(x).strip()
        and not _outcome_line_failed(str(x))
        and not is_internal_tool_outcome_line(str(x))
        and not is_tool_action_replay_line(str(x))
    ]
    if tool_lines and (not subagent or thin_subagent):
        parts.append("【工具执行记录】\n" + "\n".join(f"- {line}" for line in tool_lines[-10:]))

    return "\n\n".join(parts).strip()


async def synthesize_specialist_deliverable(
    *,
    user_message: str,
    loop_state: LoopState | None,
    agent_id: str = "",
) -> str:
    """根据子任务诉求与工具证据合成专精交付摘要（供调度层汇总，非工具状态复述）。"""
    from app.core.loop_engineering import build_loop_exit_prompt_messages
    from app.integrations.deepseek_client import (
        chat_completion_message_async,
        is_configured,
    )

    evidence = build_deliverable_evidence_block(loop_state)
    if not evidence:
        return ""
    if not is_configured():
        return evidence[:2000]

    messages = build_loop_exit_prompt_messages(
        user_message=user_message,
        loop_state=loop_state,
        extra_evidence=(
            f"【专精 hop · {((agent_id or 'specialist').strip() or 'specialist')}】"
            "写出可交给调度层的交付摘要，禁止面向最终用户的寒暄或完整终稿。"
        ),
    )
    try:
        choice = await chat_completion_message_async(
            messages=messages,
            tools=None,
            temperature=0.35,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        return content if is_substantive_deliverable(content) else ""
    except Exception:
        return ""


async def finalize_specialist_handoff(
    loop_state: LoopState | None,
    user_message: str,
    *,
    agent_id: str = "",
    session_id: str = "",
    task_id: str = "",
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> SpecialistHandoffResult:
    """专精 hop 结束：先取显式交付物，否则在具备证据时合成交付物。"""
    state = dict(loop_state or {})
    handoff = build_specialist_handoff(
        state,
        user_message,
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        citations=citations,
        kg_context=kg_context,
    )
    if handoff.ok:
        return handoff
    if is_skill_management_message(user_message):
        return handoff
    if not has_deliverable_evidence(state):
        return handoff
    deliverable = await synthesize_specialist_deliverable(
        user_message=user_message,
        loop_state=state,
        agent_id=agent_id,
    )
    if not deliverable:
        return SpecialistHandoffResult(ok=False, text="", message=None)
    state["task_deliverable"] = deliverable
    return build_specialist_handoff(
        state,
        user_message,
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        citations=citations,
        kg_context=kg_context,
    )


def _outcome_line_failed(line: str) -> bool:
    text = (line or "").strip()
    return bool(text.endswith("失败") or "：失败" in text)


def user_facing_tool_outcome_lines(loop_state: LoopState | None) -> list[str]:
    lines: list[str] = []
    for raw in (loop_state or {}).get("tool_outcome_lines") or []:
        line = str(raw or "").strip()
        if not line or _outcome_line_failed(line) or is_internal_tool_outcome_line(line):
            continue
        lines.append(line)
    return lines


def _has_successful_skill_run(loop_state: LoopState | None) -> bool:
    state = loop_state or {}
    for line in user_facing_tool_outcome_lines(state):
        if any(marker in line for marker in _SKILL_RUN_OUTCOME_MARKERS):
            return True
    if state.get("invoked_uploaded_skills") and str(state.get("last_skill_conclusion") or "").strip():
        return True
    return False


def skill_management_goal_satisfied(
    loop_state: LoopState | None,
    user_message: str,
) -> bool:
    """Skill 创建/更新/删除是否已产出可面向用户、响应诉求的结果。"""
    from app.services.agent_skill_router import skill_creation_requires_python_script

    state = loop_state or {}
    if presentable_skill_conclusion(state):
        return True

    created = [
        str(x).strip()
        for x in (state.get("created_uploaded_skills") or [])
        if str(x).strip()
    ]
    if created:
        if skill_creation_requires_python_script(user_message):
            return _has_successful_skill_run(state) and bool(
                presentable_skill_conclusion(state)
            )
        return True

    for line in user_facing_tool_outcome_lines(state):
        if not any(marker in line for marker in _SKILL_MUTATION_OUTCOME_MARKERS):
            continue
        if skill_creation_requires_python_script(user_message):
            return _has_successful_skill_run(state) and bool(
                presentable_skill_conclusion(state)
            )
        return True

    if _has_successful_skill_run(state) and presentable_skill_conclusion(state):
        return True
    return False


def incomplete_skill_management_reply(user_message: str) -> str:
    from app.services.agent_skill_router import skill_creation_requires_python_script

    if skill_creation_requires_python_script(user_message):
        return (
            "抱歉，这次还未能完成您要求的可执行技能创建与数据验证。"
            "请稍后再试，或补充要抓取的数据源与字段说明，我会继续为您处理。"
        )
    return (
        "抱歉，这次还未能完成您要求的技能创建或更新。"
        "请稍后再试，或补充更具体的要求，我会继续为您处理。"
    )


def request_fulfilled(
    loop_state: LoopState | None,
    user_message: str,
) -> bool:
    """子任务是否已有可交付成果。

    检索过程摘要不算完成；定时提醒/发送通知等写操作成功后算完成。
    """
    state = loop_state or {}
    deliverable = str(state.get("task_deliverable") or "").strip()
    if deliverable and is_substantive_deliverable(deliverable):
        return True
    if presentable_skill_conclusion(state):
        return True
    if str(state.get("deterministic_reply") or "").strip():
        return True
    if is_skill_management_message(user_message):
        return skill_management_goal_satisfied(state, user_message)
    # 定时提醒 / 发送通知等写操作已成功 → 任务完成，避免再进一轮重复调用
    if _action_outcome_reply(state):
        return True
    return False


def build_specialist_handoff(
    loop_state: LoopState | None,
    user_message: str,
    *,
    agent_id: str = "",
    session_id: str = "",
    task_id: str = "",
    citations: list[dict[str, Any]] | None = None,
    kg_context: Any = None,
) -> SpecialistHandoffResult:
    """专精智能体交还调度层的验收载荷（非面向用户的终稿）。"""
    state = loop_state or {}

    deliverable = str(state.get("task_deliverable") or "").strip()
    if deliverable and is_substantive_deliverable(deliverable):
        return _handoff_ok(deliverable, agent_id, session_id, task_id, state, citations, kg_context)

    if not request_fulfilled(state, user_message):
        return SpecialistHandoffResult(ok=False, text="", message=None)

    if is_skill_management_message(user_message):
        if skill_management_goal_satisfied(state, user_message):
            created_reply = skill_creation_user_reply(state)
            if created_reply:
                return _handoff_ok(created_reply, agent_id, session_id, task_id, state, citations, kg_context)

    presentable = presentable_skill_conclusion(state)
    if presentable:
        return _handoff_ok(presentable, agent_id, session_id, task_id, state, citations, kg_context)

    det = str(state.get("deterministic_reply") or "").strip()
    if det:
        return _handoff_ok(det, agent_id, session_id, task_id, state, citations, kg_context)

    return SpecialistHandoffResult(ok=False, text="", message=None)


def _handoff_ok(
    text: str,
    agent_id: str,
    session_id: str,
    task_id: str,
    loop_state: LoopState,
    citations: list[dict[str, Any]] | None,
    kg_context: Any,
) -> SpecialistHandoffResult:
    """构建成功的 handoff 结果（去重公共逻辑）。"""
    return build_specialist_handoff_result(
        ok=True,
        text=text,
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        loop_state=loop_state,
        citations=citations,
        kg_context=kg_context,
    )


def loop_state_has_tool_success(loop_state: LoopState | None) -> bool:
    state = loop_state or {}
    if user_facing_tool_outcome_lines(state):
        return True
    if str(state.get("last_skill_conclusion") or "").strip():
        return True
    return False


def reply_contradicts_tool_outcomes(
    content: str,
    loop_state: LoopState | None,
) -> bool:
    if not loop_state_has_tool_success(loop_state):
        return False
    return reply_looks_like_denial(content)


def _format_skill_conclusion(conclusion: str) -> str | None:
    text = (conclusion or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if looks_like_internal_agent_content(text):
            return None
        return text
    if not isinstance(data, dict):
        return text if not looks_like_internal_agent_content(text) else None

    latest = data.get("最新记录")
    if isinstance(latest, dict):
        parts = [f"**{k}**：{v}" for k, v in latest.items()]
        header = str(data.get("数据名称") or "执行结果").strip()
        source = str(data.get("数据来源") or "").strip()
        lines = [f"### {header}"]
        if source:
            lines.append(f"来源：{source}")
        lines.extend(parts)
        return "\n".join(lines)

    if data.get("conclusion"):
        inner = str(data["conclusion"]).strip()
        return _format_skill_conclusion(inner) or inner
    return None


def presentable_skill_conclusion(loop_state: LoopState | None) -> str | None:
    """脚本/工具已产出可直接展示的数据结论（带缓存）。"""
    state = loop_state or {}
    cached = state.get("_cached_presentable_conclusion")
    if cached is not None:
        return cached if cached else None

    conclusion = str(state.get("last_skill_conclusion") or "").strip()
    if not conclusion:
        state["_cached_presentable_conclusion"] = ""
        return None
    formatted = _format_skill_conclusion(conclusion)
    result = formatted if (formatted and not looks_like_internal_agent_content(formatted)) else None
    state["_cached_presentable_conclusion"] = result or ""
    return result


def format_chat_history_excerpt(
    history: list[AiChatMessage] | None,
    *,
    limit: int = 4,
) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-limit:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()
        if not text:
            continue
        if len(text) > 400:
            text = text[:400] + "…"
        lines.append(f"{role}：{text}")
    return "\n".join(lines)


def skill_creation_user_reply(loop_state: LoopState | None) -> str | None:
    """发展技能创建完成后的固定用户话术。"""
    created = [
        str(x).strip()
        for x in ((loop_state or {}).get("created_uploaded_skills") or [])
        if str(x).strip()
    ]
    if not created:
        return None
    if len(created) == 1:
        base = (
            f"好消息，{created[0]} 技能已经为您准备好了。\n\n"
            "以后有同类需求您直接说就好，我会帮您把结果整理清楚。"
        )
    else:
        names = "、".join(created)
        base = (
            f"好消息，{names} 等技能都已为您准备好了。\n\n"
            "有同类需求您直接说就好，我会按您的要求帮您查。"
        )
    detail_parts: list[str] = []
    subagent = latest_subagent_summary(loop_state)
    if subagent:
        detail_parts.append(subagent)
    sample = presentable_skill_conclusion(loop_state)
    if sample and sample not in detail_parts:
        detail_parts.append(sample)
    if detail_parts:
        return f"{base}\n\n" + "\n\n".join(detail_parts)
    return base


def build_tool_outcome_summary(loop_state: LoopState | None) -> list[str]:
    state = loop_state or {}
    presentable = presentable_skill_conclusion(state)
    if presentable:
        return [presentable]
    lines = user_facing_tool_outcome_lines(state)
    created = [str(x).strip() for x in (state.get("created_uploaded_skills") or []) if str(x).strip()]
    if created:
        lines.append(f"已创建/更新 Skill：{', '.join(created)}")
    invoked = [str(x).strip() for x in (state.get("invoked_uploaded_skills") or []) if str(x).strip()]
    if invoked:
        lines.append(f"已执行 Skill：{', '.join(invoked)}")
    conclusion = str(state.get("last_skill_conclusion") or "").strip()
    if conclusion and not presentable:
        if not looks_like_internal_agent_content(conclusion):
            lines.append(conclusion[:1200])
    return lines[-12:]


def _true_deliverable_reply(loop_state: LoopState | None) -> str | None:
    """结构化交付物（确定性答复 / 脚本结论），不含工具状态清单。"""
    from app.agentkit.message.filter import has_mermaid_deliverable

    state = loop_state or {}
    det = str(state.get("deterministic_reply") or "").strip()
    if det:
        return det
    task = str(state.get("task_deliverable") or "").strip()
    if task and (has_mermaid_deliverable(task) or is_substantive_deliverable(task)):
        return task
    presentable = presentable_skill_conclusion(state)
    if presentable:
        return presentable
    return None


def _action_outcome_reply(loop_state: LoopState | None) -> str | None:
    """已完成的动作确认（如定时通知）可作为快速回复；检索过程摘要不行。"""
    lines = [
        line
        for line in user_facing_tool_outcome_lines(loop_state)
        if not is_tool_action_replay_line(line) and not looks_like_tool_status_echo(line)
    ]
    if not lines:
        return None
    if len(lines) == 1 and "\n" in lines[0]:
        return lines[0]
    return "\n".join(f"- {line}" for line in lines)


def fallback_tool_loop_reply(user_message: str, loop_state: LoopState | None) -> str:
    """无 LLM 合成时的兜底。禁止把「联网检索返回 N 条」类过程摘要当作用户答案。"""
    deliverable = _true_deliverable_reply(loop_state)
    if deliverable:
        return deliverable
    if is_skill_management_message(user_message):
        created_reply = skill_creation_user_reply(loop_state)
        if created_reply:
            return created_reply
        if not skill_management_goal_satisfied(loop_state, user_message):
            return incomplete_skill_management_reply(user_message)
    action = _action_outcome_reply(loop_state)
    if action:
        return action
    _ = user_message
    return "抱歉，这次没能完成您的请求。您可以补充更具体的要求，或稍后再试，我会继续帮您处理。"


def _resolve_tool_loop_reply_fast(
    user_message: str,
    loop_state: LoopState | None,
) -> str | None:
    """快速路径：真正交付物 / 动作确认。检索类证据必须走 LLM 综合。"""
    state = dict(loop_state or {})
    handoff = build_specialist_handoff(state, user_message)
    if handoff.ok and handoff.text:
        return handoff.text

    from app.services.agent_skill_router import is_platform_system_data_message

    if is_platform_system_data_message(user_message):
        return (
            "未能从系统接口获取用户或组织数据。"
            "请稍后重试，或前往「系统设置 → 用户管理」查看；"
            "请勿根据猜测列出用户姓名或邮箱。"
        )

    if state.get("expects_skill_data"):
        deliverable = _true_deliverable_reply(state) or _action_outcome_reply(state)
        if deliverable:
            return deliverable
        if has_deliverable_evidence(state):
            return None  # 有检索/工具证据 → LLM 综合
        return (
            "抱歉，这次未能自动获取到您要的最新数据。"
            "请稍后再试，或补充更具体的查询条件。"
        )

    if is_skill_management_message(user_message):
        if skill_management_goal_satisfied(state, user_message):
            reply = skill_creation_user_reply(state) or _true_deliverable_reply(state)
            if reply and "没能完成" not in reply and "抱歉" not in reply[:4]:
                return reply
        return incomplete_skill_management_reply(user_message)

    from app.services.agent_skill_router import user_wants_browser_screenshot

    if user_wants_browser_screenshot(user_message) and state.get("collected_attachments"):
        return "已完成您要求的浏览器操作，页面截图如下。"

    action = _action_outcome_reply(state)
    if action:
        return action

    # 有检索正文等证据 → LLM 综合；禁止把过程摘要当答案
    if state.get("retrieval_context_parts") or presentable_skill_conclusion(state):
        return None
    if user_facing_tool_outcome_lines(state):
        # 仅过程摘要时也走综合（综合侧用 retrieval / 子结论；无材料则 fallback）
        return None

    return _true_deliverable_reply(state)


def build_tool_loop_user_synthesis_messages(
    *,
    user_message: str,
    loop_state: LoopState | None,
    memory_context: str = "",
    chat_history: list[AiChatMessage] | None = None,
) -> list[dict[str, str]]:
    from app.core.loop_engineering import build_loop_exit_prompt_messages

    return build_loop_exit_prompt_messages(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=memory_context,
        history_excerpt=format_chat_history_excerpt(chat_history),
    )


async def iter_synthesize_tool_loop_user_reply_events(
    *,
    user_message: str,
    loop_state: LoopState | None,
    memory_context: str = "",
    chat_history: list[AiChatMessage] | None = None,
    step_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """工具循环终稿：fast path 一次性返回，否则流式 LLM 合成。"""
    from app.integrations.deepseek_client import is_configured
    from app.services.llm_workflow_stream import iter_llm_answer_events

    fast = _resolve_tool_loop_reply_fast(user_message, loop_state)
    if fast is not None:
        yield {"type": "complete_text", "text": fast}
        return

    if not has_deliverable_evidence(loop_state):
        yield {
            "type": "complete_text",
            "text": fallback_tool_loop_reply(user_message, loop_state),
        }
        return

    if not is_configured():
        evidence = build_deliverable_evidence_block(loop_state)
        yield {"type": "complete_text", "text": (evidence or "")[:4000]}
        return

    messages = build_tool_loop_user_synthesis_messages(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=memory_context,
        chat_history=chat_history,
    )
    async for ev in iter_llm_answer_events(
        messages=messages,
        temperature=0.4,
        think_title="根据工具结果汇总回答",
        think_detail="根据工具结果生成结论…",
        step_id=step_id,
        skip_initial_thinking=True,
        timeout=60.0,
    ):
        yield ev


async def synthesize_tool_loop_user_reply(
    *,
    user_message: str,
    loop_state: LoopState | None,
    memory_context: str = "",
    chat_history: list[AiChatMessage] | None = None,
) -> str:
    """工具循环终稿：交付物合成后输出。"""
    parts: list[str] = []
    async for ev in iter_synthesize_tool_loop_user_reply_events(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=memory_context,
        chat_history=chat_history,
    ):
        if ev.get("type") == "delta" and ev.get("text"):
            parts.append(str(ev["text"]))
        elif ev.get("type") == "complete_text":
            return str(ev.get("text") or "").strip()
    return "".join(parts).strip() or fallback_tool_loop_reply(user_message, loop_state)
