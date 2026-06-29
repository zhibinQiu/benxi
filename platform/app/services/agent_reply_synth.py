"""工具循环结束后的用户可见回复合成 — 与 tool loop 内 assistant 正文隔离。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.agent_message_parse import (
    looks_like_internal_agent_content,
)
from app.core.aip.handoff import SpecialistHandoffResult, build_specialist_handoff_result
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_skill_router import is_skill_management_message

_DENIAL_MARKERS = (
    "无法完成",
    "无法设置",
    "无法定",
    "不能设置",
    "没法",
    "没能完成",
    "无法为您",
    "无直接创建",
    "无查询接口",
    "无定时提醒",
    "建议您手动",
    "建议使用手机",
    "手机自带",
    "手机计时器",
    "闹钟功能",
    "不具备",
    "不支持",
    "请联系系统管理员",
    "抱歉，这次没能",
)

_USER_COMMAND_RE = re.compile(
    r"run_skill_script\s*[\(\'\"]|load_uploaded_skill\s*[\(\'\"]|"
    r"示例命令|请使用示例|建议您运行|建议运行|使用命令|"
    r"args\s*=\s*\[|carbon-market-price",
    re.I,
)

# 规划/探查类工具摘要，不能当作已响应用户请求
_INTERNAL_OUTCOME_PREFIXES = (
    "Skills 目录",
    "加载 Skill",
    "搜索工具",
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
    return False


def _outcome_line_failed(line: str) -> bool:
    text = (line or "").strip()
    return bool(text.endswith("失败") or "：失败" in text)


def user_facing_tool_outcome_lines(loop_state: dict[str, Any] | None) -> list[str]:
    lines: list[str] = []
    for raw in (loop_state or {}).get("tool_outcome_lines") or []:
        line = str(raw or "").strip()
        if not line or _outcome_line_failed(line) or is_internal_tool_outcome_line(line):
            continue
        lines.append(line)
    return lines


def _has_successful_skill_run(loop_state: dict[str, Any] | None) -> bool:
    state = loop_state or {}
    for line in user_facing_tool_outcome_lines(state):
        if any(marker in line for marker in _SKILL_RUN_OUTCOME_MARKERS):
            return True
    if state.get("invoked_uploaded_skills") and str(state.get("last_skill_conclusion") or "").strip():
        return True
    return False


def skill_management_goal_satisfied(
    loop_state: dict[str, Any] | None,
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
    loop_state: dict[str, Any] | None,
    user_message: str,
) -> bool:
    """用户诉求是否已由工具/脚本落实 — 专精层与工具循环的统一结束条件。"""
    state = loop_state or {}
    if presentable_skill_conclusion(state):
        return True
    if str(state.get("deterministic_reply") or "").strip():
        return True
    if is_skill_management_message(user_message):
        return skill_management_goal_satisfied(state, user_message)
    if state.get("expects_skill_data"):
        return False
    return bool(user_facing_tool_outcome_lines(state))


def build_specialist_handoff(
    loop_state: dict[str, Any] | None,
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
    if not request_fulfilled(state, user_message):
        return SpecialistHandoffResult(ok=False, text="", message=None)

    presentable = presentable_skill_conclusion(state)
    if presentable:
        return build_specialist_handoff_result(
            ok=True,
            text=presentable,
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            loop_state=state,
            citations=citations,
            kg_context=kg_context,
        )

    det = str(state.get("deterministic_reply") or "").strip()
    if det:
        return build_specialist_handoff_result(
            ok=True,
            text=det,
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            loop_state=state,
            citations=citations,
            kg_context=kg_context,
        )

    if is_skill_management_message(user_message):
        created_reply = skill_creation_user_reply(state)
        if created_reply:
            text = created_reply
            if presentable:
                text = f"{created_reply}\n\n{presentable}"
            return build_specialist_handoff_result(
                ok=True,
                text=text,
                agent_id=agent_id,
                session_id=session_id,
                task_id=task_id,
                loop_state=state,
                citations=citations,
                kg_context=kg_context,
            )

    lines = user_facing_tool_outcome_lines(state)
    if lines:
        return build_specialist_handoff_result(
            ok=True,
            text=lines[-1],
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            loop_state=state,
            citations=citations,
            kg_context=kg_context,
        )
    return SpecialistHandoffResult(ok=False, text="", message=None)


def loop_state_has_tool_success(loop_state: dict[str, Any] | None) -> bool:
    state = loop_state or {}
    if user_facing_tool_outcome_lines(state):
        return True
    if str(state.get("last_skill_conclusion") or "").strip():
        return True
    return False


def reply_contradicts_tool_outcomes(
    content: str,
    loop_state: dict[str, Any] | None,
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


def presentable_skill_conclusion(loop_state: dict[str, Any] | None) -> str | None:
    """脚本/工具已产出可直接展示的数据结论。"""
    conclusion = str((loop_state or {}).get("last_skill_conclusion") or "").strip()
    if not conclusion:
        return None
    formatted = _format_skill_conclusion(conclusion)
    if formatted and not looks_like_internal_agent_content(formatted):
        return formatted
    return None


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


def skill_creation_user_reply(loop_state: dict[str, Any] | None) -> str | None:
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
            "以后您可以直接问我，例如「北京碳价多少」或「查一下广东最新碳价」，"
            "我会帮您把结果整理清楚。"
        )
    else:
        names = "、".join(created)
        base = (
            f"好消息，{names} 等技能都已为您准备好了。\n\n"
            "有同类需求您直接说就好，我会按您的要求帮您查。"
        )
    sample = presentable_skill_conclusion(loop_state)
    if sample:
        return f"{base}\n\n{sample}"
    return base


def build_tool_outcome_summary(loop_state: dict[str, Any] | None) -> list[str]:
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


def fallback_tool_loop_reply(user_message: str, loop_state: dict[str, Any] | None) -> str:
    det = str((loop_state or {}).get("deterministic_reply") or "").strip()
    if det:
        return det
    presentable = presentable_skill_conclusion(loop_state)
    if presentable:
        return presentable
    if is_skill_management_message(user_message):
        created_reply = skill_creation_user_reply(loop_state)
        if created_reply:
            return created_reply
        if not skill_management_goal_satisfied(loop_state, user_message):
            return incomplete_skill_management_reply(user_message)
    lines = build_tool_outcome_summary(loop_state)
    if lines:
        if len(lines) == 1 and "\n" in lines[0]:
            return lines[0]
        return "\n".join(f"- {line}" for line in lines)
    _ = user_message
    return "抱歉，这次没能完成您的请求。您可以补充更具体的要求，或稍后再试，我会继续帮您处理。"


async def synthesize_tool_loop_user_reply(
    *,
    user_message: str,
    loop_state: dict[str, Any] | None,
    memory_context: str = "",
    chat_history: list[AiChatMessage] | None = None,
) -> str:
    """调度/单体模式的用户可见出口：仅当诉求已落实时输出，否则明确未完成。"""
    _ = memory_context
    _ = chat_history

    handoff = build_specialist_handoff(loop_state, user_message)
    if handoff.ok and handoff.text:
        return handoff.text

    from app.services.agent_skill_router import is_platform_system_data_message

    if is_platform_system_data_message(user_message):
        return (
            "未能从系统接口获取用户或组织数据。"
            "请稍后重试，或前往「系统设置 → 用户管理」查看；"
            "请勿根据猜测列出用户姓名或邮箱。"
        )

    if (loop_state or {}).get("expects_skill_data"):
        return (
            "抱歉，这次未能自动获取到您要的最新数据。"
            "请稍后再试，或直接说明具体市场（例如「北京碳价多少」）。"
        )

    if is_skill_management_message(user_message):
        return incomplete_skill_management_reply(user_message)

    from app.services.agent_skill_router import user_wants_browser_screenshot

    if user_wants_browser_screenshot(user_message) and (
        loop_state or {}
    ).get("collected_attachments"):
        lines = build_tool_outcome_summary(loop_state)
        if lines:
            if len(lines) == 1 and "\n" in lines[0]:
                return lines[0]
            return "\n".join(f"- {line}" for line in lines)
        return "已完成您要求的浏览器操作，页面截图如下。"

    return (
        "抱歉，这次没能完成您的请求。您可以补充更具体的要求，或稍后再试，我会继续帮您处理。"
    )
