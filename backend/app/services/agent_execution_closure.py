"""执行闭环 — 规划后若未产出有效结果，自动补执行或重规划直至可答复。"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from app.core.agent_loop_state import LoopState

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_planner import (
    AgentExecutionPlan,
    _infer_uploaded_skill_followup,
)
from app.services.agent_reply_synth import (
    presentable_skill_conclusion,
    request_fulfilled,
)
from app.services.agent_skill_router import is_skill_management_message

MAX_ADAPTIVE_TOOL_ROUNDS_PER_PASS = 12

_CARBON_MARKET_NAMES = (
    "北京",
    "上海",
    "深圳",
    "广东",
    "天津",
    "重庆",
    "湖北",
    "福建",
    "全国",
)
_SKILL_ARGS_EXAMPLE_RE = re.compile(
    r"args\s*=\s*\[\s*([\"'])(?P<a1>[^\"']*)\1\s*,\s*([\"'])(?P<a2>[^\"']*)\3\s*\]",
    re.I,
)
_RUN_SKILL_EXAMPLE_RE = re.compile(
    r"run_skill_script\s*\(\s*skill_name\s*=\s*[\"'](?P<name>[^\"']+)[\"']",
    re.I,
)


def max_adaptive_execution_passes() -> int:
    return max(1, int(getattr(get_settings(), "agent_max_adaptive_passes", 4) or 4))


def tool_rounds_for_adaptive_pass(base_rounds: int, adaptive_pass: int) -> int:
    if adaptive_pass <= 0:
        return max(1, base_rounds)
    return max(1, min(MAX_ADAPTIVE_TOOL_ROUNDS_PER_PASS, base_rounds))


def resolve_target_uploaded_skill(
    *,
    execution_plan: AgentExecutionPlan,
    loop_state: LoopState,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    uploaded_names: set[str],
) -> str | None:
    skill = str(execution_plan.uploaded_skill or "").strip()
    if skill:
        return skill
    skill = str(loop_state.get("planned_uploaded_skill") or "").strip()
    if skill:
        return skill
    invoked = list(loop_state.get("invoked_uploaded_skills") or [])
    if len(invoked) == 1:
        return str(invoked[0]).strip() or None
    created = list(loop_state.get("created_uploaded_skills") or [])
    if len(created) == 1 and not is_skill_management_message(user_message):
        return str(created[0]).strip() or None
    return _infer_uploaded_skill_followup(user_message, chat_history, uploaded_names)


def infer_skill_script_args(
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    skill_md: str,
) -> list[str]:
    """从用户消息与 SKILL.md 示例推断 run_skill_script 参数。"""
    msg = (user_message or "").strip()
    md = skill_md or ""

    for market in _CARBON_MARKET_NAMES:
        if market in msg:
            if "地方" in md or "地方" in md.lower():
                return ["地方", market]
            return [market]

    example = _SKILL_ARGS_EXAMPLE_RE.search(md)
    if example and len(msg) <= 24:
        prefix = example.group("a1")
        if prefix and prefix not in msg:
            return [prefix, msg]
        return [msg or example.group("a2")]

    if len(msg) <= 48 and msg:
        return [msg]

    from app.core.conversation_turn_context import is_likely_follow_up

    if not is_likely_follow_up(msg, chat_history):
        return [msg] if msg else []

    for item in reversed(chat_history or []):
        if item.role != "user":
            continue
        text = (item.content or "").strip()
        if not text or text == msg:
            continue
        nested = infer_skill_script_args(text, None, md)
        if nested:
            return nested
    return [msg] if msg else []


def execution_plan_needs_skill_data(
    execution_plan: AgentExecutionPlan,
    user_message: str,
    *,
    plan_has_script: bool | None,
) -> bool:
    if is_skill_management_message(user_message):
        return False
    if execution_plan.direct_answer:
        return False
    if execution_plan.intent == "执行发展技能":
        return True
    if execution_plan.uploaded_skill and plan_has_script is not False:
        return True
    return False


def build_skill_management_continue_nudge(
    user_message: str,
    loop_state: LoopState,
) -> str:
    """诉求尚未落实时，提示专精智能体继续调用工具（非用户可见）。"""
    created = [
        str(x).strip()
        for x in (loop_state.get("created_uploaded_skills") or [])
        if str(x).strip()
    ]
    if created:
        name = created[0]
        return (
            f"【系统】用户诉求尚未完成。Skill `{name}` 已创建时须 run_skill_script 验证；"
            "否则 create/update 后 run 验证。禁止把目录列表或中间步骤当作结果交还。"
        )
    return (
        "【系统】用户诉求尚未完成。请继续通过 tool_calls 落实："
        "直接 create_skill（数据类含 main.py）并 run_skill_script 验证新包。"
        "勿 list/load 已有技能。禁止把中间输出当作完成。"
    )


def execution_goal_satisfied(
    execution_plan: AgentExecutionPlan,
    loop_state: LoopState,
    user_message: str,
    *,
    plan_has_script: bool | None,
) -> bool:
    _ = execution_plan
    _ = plan_has_script
    if presentable_skill_conclusion(loop_state):
        return True
    if str((loop_state or {}).get("deterministic_reply") or "").strip():
        return True
    return request_fulfilled(loop_state, user_message)


def replan_after_missing_skill_data(
    *,
    message: str,
    history: list[AiChatMessage] | None,
    uploaded_names: set[str],
    prior_plan: AgentExecutionPlan,
    loop_state: LoopState,
) -> AgentExecutionPlan | None:
    """确定性重规划：上一轮未拿到脚本数据，必须执行发展技能。"""
    skill = resolve_target_uploaded_skill(
        execution_plan=prior_plan,
        loop_state=loop_state,
        user_message=message,
        chat_history=history,
        uploaded_names=uploaded_names,
    )
    if not skill:
        return None
    outcomes = loop_state.get("tool_outcome_lines") or []
    detail = "；".join(str(x) for x in outcomes[-3:]) if outcomes else "未产出有效数据"
    return replace(
        prior_plan,
        reasoning=f"上一轮未获得有效脚本结论（{detail}），须直接 run_skill_script",
        intent="执行发展技能",
        direct_answer=False,
        allowed_tools=(),
        uploaded_skill=skill,
        steps=(f"立即 run_skill_script({skill}) 获取数据", "结束"),
        source="replan",
    )


def build_forced_skill_execution_nudge(
    skill_name: str,
    args: list[str],
) -> str:
    args_json = json.dumps(args, ensure_ascii=False)
    return (
        f"【系统·重规划】上一轮未拿到有效数据。你必须通过 tool_calls 调用 "
        f"run_skill_script(skill_name=\"{skill_name}\", args={args_json})，"
        "禁止在正文中让用户自行执行命令或假装已有数据。"
    )


def build_adaptive_replan_notice(
    *,
    prior_plan: AgentExecutionPlan,
    new_plan: AgentExecutionPlan,
    loop_state: LoopState,
) -> str:
    outcomes = loop_state.get("tool_outcome_lines") or []
    tail = "；".join(str(x) for x in outcomes[-3:]) if outcomes else "尚无有效结果"
    return (
        f"【系统·自适应重规划】用户任务尚未完成（{tail}）。"
        f"新方案：{new_plan.intent or new_plan.reasoning}；"
        f"步骤：{' → '.join(new_plan.steps[:4]) if new_plan.steps else '按新规划执行'}。"
        f"（上轮：{prior_plan.intent}）"
    )


def apply_execution_plan_unlocks(
    execution_plan: AgentExecutionPlan,
    loop_state: LoopState,
) -> None:
    from app.services.agent_planner import SKILL_MGMT_INTENT
    from app.services.agent_tool_search import register_unlocked_tools

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill
    unlock_names: list[str] = []
    if execution_plan.uploaded_skill:
        unlock_names.append("run_skill_script")
    if execution_plan.intent == SKILL_MGMT_INTENT:
        unlock_names.extend(
            [
                "run_skill_script",
                "create_skill",
                "update_uploaded_skill_file",
                "delete_uploaded_skill",
            ]
        )
    if unlock_names:
        register_unlocked_tools(loop_state, unlock_names)


async def resolve_adaptive_replan(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[AiChatMessage] | None,
    intent_plan: Any,
    available_atomic_tools: set[str] | None,
    kg_planning_context: str | None,
    prior_plan: AgentExecutionPlan,
    loop_state: LoopState,
    uploaded_names: set[str],
) -> AgentExecutionPlan:
    """确定性重规划：仅补执行发展技能，不再二次 LLM 规划。"""
    _ = db, user, intent_plan, available_atomic_tools, kg_planning_context
    deterministic = replan_after_missing_skill_data(
        message=message,
        history=history,
        uploaded_names=uploaded_names,
        prior_plan=prior_plan,
        loop_state=loop_state,
    )
    if deterministic is not None:
        return deterministic

    if request_fulfilled(loop_state, message):
        return prior_plan

    skill = resolve_target_uploaded_skill(
        execution_plan=prior_plan,
        loop_state=loop_state,
        user_message=message,
        chat_history=history,
        uploaded_names=uploaded_names,
    )
    if skill:
        return replace(
            prior_plan,
            reasoning="继续执行发展技能直至诉求落实",
            intent="执行发展技能",
            direct_answer=False,
            allowed_tools=(),
            uploaded_skill=skill,
            steps=(f"run_skill_script({skill})",),
            source="replan",
        )
    return prior_plan


async def auto_execute_uploaded_skill(
    db,
    user,
    *,
    skill_name: str,
    user_message: str,
    chat_history: list[AiChatMessage] | None,
    loop_state: LoopState,
    conversation_id: str | None,
    attachment_session_id: str | None,
) -> tuple[bool, str]:
    """服务端代用户执行 run_skill_script，写入 loop_state。"""
    from app.services.agent_skill_service import uploaded_skill_has_script
    from app.services.agent_tools import execute_agent_tool, fetch_uploaded_skill_md

    name = (skill_name or "").strip()
    if not name:
        return False, "缺少 skill_name"
    if not uploaded_skill_has_script(db, name):
        return False, f"Skill `{name}` 无脚本"

    skill_md = fetch_uploaded_skill_md(db, name, user=user, max_chars=6000) or ""
    args = infer_skill_script_args(user_message, chat_history, skill_md)

    loop_state["planned_uploaded_skill"] = name
    invoked = list(loop_state.get("invoked_uploaded_skills") or [])
    if name not in invoked:
        invoked.append(name)
    loop_state["invoked_uploaded_skills"] = invoked

    result_text = await execute_agent_tool(
        db,
        user,
        tool_name="run_skill_script",
        arguments={"skill_name": name, "args": args},
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        user_message=user_message,
        loop_state=loop_state,
    )
    try:
        body = json.loads(result_text)
        ok = bool(body.get("ok"))
        summary = str(body.get("summary") or "")
    except json.JSONDecodeError:
        ok = False
        summary = result_text[:200]

    outcome_lines = list(loop_state.get("tool_outcome_lines") or [])
    outcome_lines.append(f"自动执行 Skill：{summary or ('完成' if ok else '失败')}")
    loop_state["tool_outcome_lines"] = outcome_lines[-12:]
    return ok and bool(presentable_skill_conclusion(loop_state)), summary
