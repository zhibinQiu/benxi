"""对话上下文裁剪 — 控制 LLM prompt 中的历史轮次与字符预算。"""

from __future__ import annotations

from typing import Any, Sequence

from app.agentkit.message.context import trim_chat_history as _trim_chat_history

DEFAULT_MAX_HISTORY_MESSAGES = 8
DEFAULT_HISTORY_CHAR_BUDGET = 6_000


def trim_chat_history(
    history: Sequence[Any] | None,
    *,
    max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES,
    max_chars: int = DEFAULT_HISTORY_CHAR_BUDGET,
) -> list[Any]:
    """从最新消息往回保留，同时受条数与总字符数约束。"""
    return _trim_chat_history(
        history,
        max_messages=max_messages,
        max_chars=max_chars,
    )
