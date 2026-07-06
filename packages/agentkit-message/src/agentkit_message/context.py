"""多轮对话上下文管理 — 追问检测、历史裁剪、上下文摘要。"""

from __future__ import annotations

import re
from typing import Any, Sequence, TypeVar

_CONTEXT_HISTORY_MAX_MESSAGES = 8
_CONTEXT_HISTORY_CHAR_BUDGET = 6_000

# ── 追问检测 ──────────────────────────────────────────────────────────────────

_FOLLOWUP_RE = re.compile(
    r"(?:继续|然后|还有|进一步|详细|展开|具体|再说说|刚才|上面|前述|前面说的|"
    r"第二点|第三点|上一条|补充一下|同样|同理|也查|再查|那|这|那个|这个|"
    r"换成|改为|改成|另外|除此之外|除此之外呢)"
)

_SHORT_FOLLOWUP_TAIL_RE = re.compile(r"(?:呢|吗|吧|啊|呀)[？?]?$")

# 完整独立问句
_STANDALONE_QUESTION_RE = re.compile(
    r"(?:什么|为何|为什么|怎么|如何|怎样|能不能|可不可以|哪些|哪个|多少|几步|有没有|是否)"
    r"|(?:需要|应该|可否).{0,12}(?:几|多少|什么|怎么|如何)"
    r"|[？?]$",
    re.I,
)

_STANDALONE_CHITCHAT_RE = re.compile(
    r"^(?:嗯|哦|啊|哈|好|行|可以|不错|厉害|哈哈|谢谢|感谢|多谢|"
    r"辛苦了|没事了|算了|好吧|就这样|收到|明白|知道了)(?:[!！?？。.,，~～\s]*)$",
    re.I,
)

_EXPLICIT_GREETING_RE = re.compile(
    r"^(?:"
    r"你好|您好|hi|hello|hey|嗨|早上好|下午好|晚上好|"
    r"你是谁|你是哪位|你叫什么|你是谁啊|你谁啊|你是？|"
    r"你是什么|你是什么模型|你是啥|你是哪个模型|你是哪个助手|"
    r"介绍一下自己|介绍你自己|自我介绍|"
    r"谢谢|感谢|多谢|辛苦了|"
    r"再见|拜拜|bye|"
    r"好的|好哒|明白|知道了|收到|没问题|ok|okay|"
    r"在吗|在不在|"
    r"你能做什么|你会什么|你能帮我什么|有什么功能|"
    r"(?:随便)?聊聊|闲聊一下|闲聊|讲个笑话"
    r")(?:[!！?？呀啊吧呢嘛。.,，~～\s]*)$",
    re.I,
)

T = TypeVar("T")


def is_explicit_greeting_or_chitchat(message: str) -> bool:
    """当前输入是否为独立寒暄（不应绑定上文业务话题）。"""
    text = (message or "").strip()
    if not text:
        return True
    return bool(_EXPLICIT_GREETING_RE.match(text) or _STANDALONE_CHITCHAT_RE.match(text))


def is_standalone_question(message: str) -> bool:
    """当前输入是否像完整独立问题（非对上文的短跟帖）。"""
    text = (message or "").strip()
    if not text:
        return False
    if _FOLLOWUP_RE.search(text):
        return False
    if _SHORT_FOLLOWUP_TAIL_RE.search(text):
        return False
    return bool(_STANDALONE_QUESTION_RE.search(text))


def is_likely_follow_up(
    message: str,
    history: Sequence[Any] | None,
    *,
    message_content_attr: str = "content",
    message_role_attr: str = "role",
    user_role_value: str = "user",
    assistant_role_value: str = "assistant",
) -> bool:
    """判断当前输入是否像对上文的追问/补充。

    Args:
        message: 当前用户输入。
        history: 历史消息列表。
        message_content_attr: 消息对象中的 content 属性名。
        message_role_attr: 消息对象中的 role 属性名。
        user_role_value: 用户消息的 role 值。
        assistant_role_value: 助手消息的 role 值。
    Returns:
        True 表示当前输入是追问。
    """
    text = (message or "").strip()
    if not text or not history:
        return False
    if is_explicit_greeting_or_chitchat(text):
        return False
    if is_standalone_question(text):
        return False
    if _FOLLOWUP_RE.search(text):
        return True

    last_assistant = _last_message_by_role(
        history, assistant_role_value,
        content_attr=message_content_attr, role_attr=message_role_attr,
    )
    if len(text) <= 32 and last_assistant:
        if _SHORT_FOLLOWUP_TAIL_RE.search(text):
            return True
        if len(text) <= 8:
            return True
    return False


def _last_message_by_role(
    history: Sequence[Any],
    role: str,
    *,
    content_attr: str = "content",
    role_attr: str = "role",
) -> str:
    for item in reversed(history):
        r = _get_field(item, role_attr)
        if r != role:
            continue
        text = str(_get_field(item, content_attr) or "").strip()
        if text:
            return text
    return ""


def _get_field(obj: Any, field: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _content_len(msg: Any, *, content_attr: str = "content") -> int:
    return len(str(_get_field(msg, content_attr) or ""))


def trim_chat_history(
    history: Sequence[T] | None,
    *,
    max_messages: int = _CONTEXT_HISTORY_MAX_MESSAGES,
    max_chars: int = _CONTEXT_HISTORY_CHAR_BUDGET,
    content_attr: str = "content",
) -> list[T]:
    """从最新消息往回保留历史，同时受条数与总字符数约束。

    Args:
        history: 历史消息列表（可为 None）。
        max_messages: 最多保留条数。
        max_chars: 最多保留字符数。
        content_attr: 消息对象中的 content 属性名。
    Returns:
        裁剪后的历史消息列表（按时间从旧到新）。
    """
    if not history:
        return []

    cap = max(1, max_messages)
    budget = max(500, max_chars)
    tail = list(history[-cap:])

    kept: list[T] = []
    total = 0
    for item in reversed(tail):
        size = _content_len(item, content_attr=content_attr)
        if kept and total + size > budget:
            break
        kept.insert(0, item)
        total += size
    return kept


def format_conversation_snippet(
    history: Sequence[Any] | None,
    *,
    limit: int = 8,
    per_message_chars: int = 240,
    role_labels: dict[str, str] | None = None,
    content_attr: str = "content",
    role_attr: str = "role",
) -> str:
    """将历史消息格式化为可读的对话摘要字符串。

    Args:
        history: 历史消息列表。
        limit: 最多展示的条目数。
        per_message_chars: 每条消息最多取前 N 字符。
        role_labels: 角色标签映射，如 {"user": "用户", "assistant": "助手"}。
        content_attr: 消息对象的 content 属性名。
        role_attr: 消息对象的 role 属性名。
    Returns:
        格式化后的对话摘要文本，每条消息一行。
    """
    if not history:
        return ""
    labels = role_labels or {"user": "用户", "assistant": "助手"}
    lines: list[str] = []
    for msg in history[-limit:]:
        role = _get_field(msg, role_attr)
        label = labels.get(role, str(role))
        text = str(_get_field(msg, content_attr) or "").strip()[:per_message_chars]
        if text:
            lines.append(f"{label}：{text}")
    return "\n".join(lines)
