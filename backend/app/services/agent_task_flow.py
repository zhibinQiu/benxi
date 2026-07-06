"""Agent 任务流辅助 — 调度层路由专精；专精层只交还 handoff，由调度汇总后答复用户。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    AgentToolPlan,
    is_chitchat_message,
    needs_knowledge_retrieval,
    needs_web_search,
)
from app.services.agent_skill_router import is_platform_usage_message, is_platform_operation_message, is_platform_system_data_message
from app.core.conversation_turn_context import (
    build_turn_planning_context,
    is_likely_follow_up,
)

_SCHEDULER_HINT_RE = re.compile(
    r"(?:定时|延迟|提醒|通知).{0,16}后|"
    r"\d+\s*(?:s|sec|秒|分钟?|min|小时?|h).{0,8}后",
    re.I,
)


@dataclass(frozen=True, slots=True)
class TaskAnalysis:
    """对用户诉求的结构化理解（分析阶段产出）。"""

    summary: str
    intent: str
    user_goal: str


def derive_task_analysis(
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    history: list[AiChatMessage] | None = None,
) -> TaskAnalysis:
    """基于消息与上下文归纳用户诉求（内部辅助，不单独展示为确认步骤）。"""
    text = (message or "").strip()
    cues: list[str] = []

    if intent_plan and intent_plan.use_attachment:
        cues.append("已提供临时附件，优先依据附件内容作答")
    if is_chitchat_message(text, history):
        cues.append("日常交流或简短问答")
    elif is_platform_operation_message(text):
        cues.append("平台系统操作（文档库/待办/用户组织等）")
    elif is_platform_usage_message(text):
        cues.append("平台功能或操作相关")
    elif is_platform_system_data_message(text):
        cues.append("平台用户/组织等系统数据查询")
    elif _SCHEDULER_HINT_RE.search(text):
        cues.append("需设置延迟/定时通知或安排定时任务")
    elif needs_knowledge_retrieval(text, history):
        cues.append("需检索知识库或文档资料")
    elif needs_web_search(text, history):
        cues.append("需联网或检索公开信息")
    else:
        cues.append("按诉求选择合适工具完成")

    summary = "；".join(cues)
    intent = (intent_plan.intent_label if intent_plan else "") or "处理用户请求"
    if is_likely_follow_up(text, history):
        goal = build_turn_planning_context(text, history)[:480] or text[:240]
    else:
        goal = text[:240] if text else "（空消息）"
    return TaskAnalysis(summary=summary, intent=intent, user_goal=goal)
