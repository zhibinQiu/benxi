"""agentkit-message: LLM 消息解析、内嵌工具调用提取、内容过滤。"""

from agentkit_message.context import (
    format_conversation_snippet,
    is_likely_follow_up,
    trim_chat_history,
)
from agentkit_message.filter import (
    ContentFilter,
    looks_like_internal_content,
    sanitize_agent_reply,
)
from agentkit_message.parse import (
    DsmlStreamFilter,
    content_has_tool_markup,
    extract_embedded_tool_calls,
    normalize_assistant_message,
    strip_tool_markup,
)

__all__ = [
    "content_has_tool_markup",
    "extract_embedded_tool_calls",
    "strip_tool_markup",
    "normalize_assistant_message",
    "DsmlStreamFilter",
    "ContentFilter",
    "looks_like_internal_content",
    "sanitize_agent_reply",
    "is_likely_follow_up",
    "trim_chat_history",
    "format_conversation_snippet",
]

__version__ = "4.6.0"
