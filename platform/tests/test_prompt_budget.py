"""prompt 字符预算单元测试。"""

from __future__ import annotations

from app.core.prompt_budget import (
    build_bounded_chat_messages,
    fit_messages_to_total_budget,
    get_prompt_limits,
)


class _Turn:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def test_fit_messages_drops_oldest_history():
    rows = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1" * 100},
        {"role": "assistant", "content": "a1" * 100},
        {"role": "user", "content": "u2" * 100},
    ]
    out = fit_messages_to_total_budget(rows, 350)
    assert out[-1]["content"].startswith("u2")
    assert len(out) < len(rows)


def test_build_bounded_chat_messages_respects_context_budget():
    history = [_Turn("user", "历史问题"), _Turn("assistant", "历史回答")]
    messages = build_bounded_chat_messages(
        system="你是助手",
        history=history,
        user_message="当前问题",
        retrieval_context="x" * 20000,
        context_instruction="参考材料",
    )
    limits = get_prompt_limits()
    total = sum(len(m["content"]) for m in messages)
    assert total <= limits["prompt_max_chars"]
    assert messages[-1]["role"] == "user"
