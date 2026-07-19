"""Loop Engineering — agentkit-loop 适配（注入平台 planner / 观测层）。"""

from __future__ import annotations

from typing import Any

from app.core.agent_loop_state import LoopState

from app.agentkit.loop import LoopEvidence, LoopExitRequest, build_loop_exit_prompt_messages as _build_loop_exit

# 平台终稿契约（含简体中文要求）
LOOP_SYSTEM_CONTRACT = (
    "Agent 循环终稿阶段。依据下方「目标、智能体计划、观测证据」生成面向用户的答复（简体中文）。"
    "若存在「子智能体结论」，以其为首要事实来源，勿复述早期检索或中间工具状态；"
    "只引用证据中的事实。\n\n"
    "【关键约束】\n"
    "1. 禁止以工具调用清单作为回复——直接回答用户问题，不要罗列你做了哪些搜索。\n"
    "   ❌ 错误示例：「使用联网搜索查询「金融专业」：联网检索返回8条」\n"
    "   ✅ 正确示例：「根据最新的就业数据，金融专业应届生的平均起薪约为...」\n"
    "2. 禁止复述「搜索了X关键词」「检索返回X条」「已读全文X条」等操作过程。\n"
    "3. 如果确实无法完成（无可用工具/技能），如实告知用户并说明原因。\n"
    "4. 禁止编造数据。\n"
    "5. 禁止让用户自行执行命令。"
)


def build_agent_generated_instruction(loop_state: LoopState | None) -> str:
    """从 loop_state 中的执行计划提取智能体自生成的任务指令。"""
    from app.agentkit.loop import AgentExecutionPlan, build_agent_instruction_from_plan
    from app.services.agent_planner import build_plan_context_instruction

    plan = (loop_state or {}).get("_execution_plan")
    if not isinstance(plan, AgentExecutionPlan):
        return ""
    return build_agent_instruction_from_plan(plan, format_plan=build_plan_context_instruction)


def _platform_loop_evidence(
    loop_state: LoopState | None,
    *,
    extra_evidence: str = "",
    history_excerpt: str = "",
) -> LoopEvidence:
    from app.core.agent_tool_context import build_turn_executed_tools_context
    from app.services.agent_reply_synth import build_deliverable_evidence_block

    return LoopEvidence(
        plan_instruction=build_agent_generated_instruction(loop_state),
        tool_context=build_turn_executed_tools_context(loop_state),
        deliverable_evidence=build_deliverable_evidence_block(loop_state),
        extra_evidence=extra_evidence,
        history_excerpt=history_excerpt,
    )


def build_loop_exit_prompt_messages(
    *,
    user_message: str,
    loop_state: LoopState | None = None,
    memory_context: str = "",
    extra_evidence: str = "",
    history_excerpt: str = "",
) -> list[dict[str, str]]:
    """循环退出阶段的动态 Prompt：system=契约，user=目标+计划+观测。"""
    return _build_loop_exit(
        LoopExitRequest(
            user_message=user_message,
            loop_state=loop_state,
            memory_context=memory_context,
            system_contract=LOOP_SYSTEM_CONTRACT,
        ),
        evidence=_platform_loop_evidence(
            loop_state,
            extra_evidence=extra_evidence,
            history_excerpt=history_excerpt,
        ),
    )
