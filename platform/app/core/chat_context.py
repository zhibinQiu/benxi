"""对话上下文裁剪 — 控制 LLM prompt 中的历史轮次与字符预算。"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

DEFAULT_MAX_HISTORY_MESSAGES = 8
DEFAULT_HISTORY_CHAR_BUDGET = 6_000


class _ChatTurn(Protocol):
    role: str
    content: str


def trim_chat_history(
    history: Sequence[Any] | None,
    *,
    max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES,
    max_chars: int = DEFAULT_HISTORY_CHAR_BUDGET,
) -> list[Any]:
    """从最新消息往回保留，同时受条数与总字符数约束。"""
    if not history:
        return []

    cap = max(1, max_messages)
    budget = max(500, max_chars)
    tail = list(history[-cap:])

    kept: list[Any] = []
    total = 0
    for item in reversed(tail):
        if isinstance(item, dict):
            content = str(item.get("content") or "")
        else:
            content = str(getattr(item, "content", None) or "")
        size = len(content.strip())
        if kept and total + size > budget:
            break
        kept.insert(0, item)
        total += size
    return kept
