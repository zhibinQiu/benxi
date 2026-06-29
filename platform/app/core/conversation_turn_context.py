"""多轮对话上下文 — 识别追问并将当前输入与上文合并供规划/思考使用。"""

from __future__ import annotations

import re

from app.schemas.ai_chat import AiChatMessage

_FOLLOWUP_RE = re.compile(
    r"(?:继续|然后|还有|进一步|详细|展开|具体|再说说|刚才|上面|前述|前面说的|"
    r"第二点|第三点|上一条|补充一下|同样|同理|也查|再查|那|这|那个|这个|"
    r"换成|改为|改成|另外|除此之外|除此之外呢)"
)

_SHORT_FOLLOWUP_TAIL_RE = re.compile(r"(?:呢|吗|吧|啊|呀)[？?]?$")

_STANDALONE_CHITCHAT_RE = re.compile(
    r"^(?:嗯|哦|啊|哈|好|行|可以|不错|厉害|哈哈|谢谢|感谢|多谢|"
    r"辛苦了|没事了|算了|好吧|就这样|收到|明白|知道了)(?:[!！?？。.,，~～\s]*)$",
    re.I,
)


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


def is_likely_follow_up(
    message: str,
    history: list[AiChatMessage] | None,
) -> bool:
    """当前输入是否像对上文的追问/补充（勿孤立解读）。"""
    text = (message or "").strip()
    if not text or not has_prior_turns(history):
        return False
    if _STANDALONE_CHITCHAT_RE.match(text):
        return False
    if _FOLLOWUP_RE.search(text):
        return True
    if len(text) <= 32 and last_assistant_message(history):
        if _SHORT_FOLLOWUP_TAIL_RE.search(text):
            return True
        if len(text) <= 16:
            return True
    return False


def format_conversation_snippet(
    history: list[AiChatMessage] | None,
    *,
    limit: int = 8,
    per_message_chars: int = 240,
) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-limit:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:per_message_chars]
        if text:
            lines.append(f"{role}：{text}")
    return "\n".join(lines)


def build_turn_planning_context(
    message: str,
    history: list[AiChatMessage] | None,
) -> str:
    """供规划/思考使用的综合上下文（短追问时合并上文）。"""
    current = (message or "").strip()
    parts: list[str] = []
    if current:
        parts.append(f"当前输入：{current[:800]}")
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
