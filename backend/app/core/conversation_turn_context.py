"""多轮对话上下文 — 识别追问并将当前输入与上文合并供规划/思考使用。

核心检测逻辑委托 ``agentkit-message``，本层保留平台 AiChatMessage 适配。"""

from __future__ import annotations

from agentkit_message.context import (
    is_likely_follow_up as _is_likely_follow_up,
)
from app.schemas.ai_chat import AiChatMessage


def is_explicit_greeting_or_chitchat(message: str) -> bool:
    """当前输入是否为独立寒暄（勿绑定上文业务话题）。"""
    from agentkit_message.context import is_explicit_greeting_or_chitchat as _check

    return _check(message)


def has_prior_turns(history: list[AiChatMessage] | None) -> bool:
    return bool(history)


def _last_message_by_role(
    history: list[AiChatMessage] | None,
    role: str,
) -> str:
    for item in reversed(history or []):
        if item.role != role:
            continue
        text = (item.content or "").strip()
        if text:
            return text
    return ""


def last_user_message(history: list[AiChatMessage] | None) -> str:
    return _last_message_by_role(history, "user")


def last_assistant_message(history: list[AiChatMessage] | None) -> str:
    return _last_message_by_role(history, "assistant")


def first_user_message(history: list[AiChatMessage] | None) -> str:
    for item in history or []:
        if item.role != "user":
            continue
        text = (item.content or "").strip()
        if text:
            return text
    return ""


def is_standalone_question(message: str) -> bool:
    """当前输入是否像完整独立问题（非对上文的短跟贴）。"""
    from agentkit_message.context import is_standalone_question as _check

    return _check(message)


def effective_history_for_context(
    message: str,
    history: list[AiChatMessage] | None,
) -> list[AiChatMessage] | None:
    """仅在上文相关时携带 history，避免无关新话题污染路由与技能匹配。"""
    if not history or not is_likely_follow_up(message, history):
        return None
    return history


def is_likely_follow_up(
    message: str,
    history: list[AiChatMessage] | None,
) -> bool:
    """当前输入是否像对上文的追问/补充（勿孤立解读）。"""
    return _is_likely_follow_up(
        message,
        history,
        message_content_attr="content",
        message_role_attr="role",
        user_role_value="user",
        assistant_role_value="assistant",
    )


def format_conversation_snippet(
    history: list[AiChatMessage] | None,
    *,
    limit: int = 8,
    per_message_chars: int = 240,
) -> str:
    from agentkit_message.context import format_conversation_snippet as _format

    return _format(
        history,
        limit=limit,
        per_message_chars=per_message_chars,
        role_labels={"user": "用户", "assistant": "助手"},
        content_attr="content",
        role_attr="role",
    )


def build_turn_planning_context(
    message: str,
    history: list[AiChatMessage] | None,
) -> str:
    """供规划/思考使用的综合上下文（短追问时合并上文）。"""
    current = (message or "").strip()
    parts: list[str] = []
    if current:
        parts.append(f"当前输入：{current[:800]}")
    if not is_likely_follow_up(message, history):
        return "\n\n".join(parts)
    first_user = first_user_message(history)
    if first_user and first_user != current:
        parts.append(f"会话首轮诉求：{first_user[:800]}")
    last_user = last_user_message(history)
    if last_user and last_user not in {current, first_user}:
        parts.append(f"上一轮用户问题：{last_user[:800]}")
    last_reply = last_assistant_message(history)
    if last_reply:
        snippet = last_reply[:1200]
        if len(last_reply) > 1200:
            snippet += "…"
        parts.append(f"上一轮助手答复摘要：{snippet}")
    hist = format_conversation_snippet(history)
    if hist:
        parts.append(f"近期对话：\n{hist}")
    return "\n\n".join(parts)


def effective_question_for_retrieval(
    message: str,
    history: list[AiChatMessage] | None,
) -> str:
    """检索/图谱规划用的问题文本：追问时带上上文主题。"""
    msg = (message or "").strip()
    if not msg or not is_likely_follow_up(msg, history):
        return msg
    anchor = last_user_message(history) or first_user_message(history)
    if anchor and anchor != msg:
        return f"{anchor}；追问：{msg}"
    return msg


def plan_cache_applicable(
    message: str,
    history: list[AiChatMessage] | None,
) -> bool:
    """多轮追问不复用仅按单句匹配的规划缓存。"""
    return not is_likely_follow_up(message, history)


def follow_up_thinking_hint(
    message: str,
    history: list[AiChatMessage] | None,
) -> str:
    """思考过程 UI 用：提示当前为连续对话中的追问。"""
    if not is_likely_follow_up(message, history):
        return ""
    anchor = last_user_message(history) or first_user_message(history)
    if anchor:
        return f"结合上文「{anchor[:80]}」理解本轮追问"
    return "结合会话上文理解本轮追问"
