"""LLM prompt 字符预算 — 控制单次对话请求的 input token 消耗。"""

from __future__ import annotations

from typing import Any, Sequence

from app.config import Settings, get_settings
from app.core.chat_context import trim_chat_history
from app.core.text_utils import truncate_text

_TRUNC_SUFFIX = "\n…（为控制 token 已截断）"


def get_prompt_limits(settings: Settings | None = None) -> dict[str, int]:
    s = settings or get_settings()
    return {
        "prompt_max_chars": max(4000, s.chat_prompt_max_chars),
        "report_prompt_max_chars": max(8000, s.chat_report_prompt_max_chars),
        "history_max_chars": max(500, s.chat_history_max_chars),
        "history_max_messages": max(2, s.chat_history_max_messages),
        "context_max_chars": max(1000, s.chat_context_max_chars),
        "report_context_max_chars": max(2000, s.chat_report_context_max_chars),
        "user_max_chars": max(500, s.chat_user_message_max_chars),
        "max_output_tokens": max(0, s.chat_max_output_tokens),
    }


def truncate_to_budget(text: str, budget: int, *, suffix: str = _TRUNC_SUFFIX) -> str:
    return truncate_text(text or "", max(1, budget), suffix=suffix)


def _content_len(msg: dict[str, Any]) -> int:
    return len(str(msg.get("content") or ""))


def fit_messages_to_total_budget(
    messages: list[dict[str, Any]],
    max_total: int,
) -> list[dict[str, Any]]:
    """在总字符上限内裁剪消息列表：优先保留 system 骨架、最近 history 与当前 user。"""
    if not messages:
        return []

    rows: list[dict[str, Any]] = []
    for m in messages:
        row: dict[str, Any] = {
            "role": str(m.get("role") or "user"),
            "content": str(m.get("content") or ""),
        }
        if m.get("tool_calls"):
            row["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            row["tool_call_id"] = m["tool_call_id"]
        rows.append(row)
    total = sum(_content_len(m) for m in rows)
    if total <= max_total:
        return rows

    has_system = rows[0]["role"] == "system"
    history_start = 1 if has_system else 0
    user_idx = len(rows) - 1

    while total > max_total and user_idx - history_start > 0:
        removed = _content_len(rows[history_start])
        rows.pop(history_start)
        user_idx -= 1
        total -= removed

    while total > max_total and user_idx - history_start > 0:
        content = rows[history_start]["content"]
        if len(content) <= 120:
            removed = _content_len(rows[history_start])
            rows.pop(history_start)
            user_idx -= 1
            total -= removed
            continue
        rows[history_start]["content"] = truncate_to_budget(content, max(120, len(content) // 2))
        total = sum(_content_len(m) for m in rows)

    if total > max_total and has_system:
        others = sum(_content_len(m) for m in rows[1:])
        allowed = max(400, max_total - others)
        rows[0]["content"] = truncate_to_budget(rows[0]["content"], allowed)
        total = sum(_content_len(m) for m in rows)

    if total > max_total and rows:
        others = sum(_content_len(m) for m in rows[:-1])
        allowed = max(200, max_total - others)
        rows[-1]["content"] = truncate_to_budget(rows[-1]["content"], allowed)

    return rows


def build_bounded_chat_messages(
    *,
    system: str,
    history: Sequence[Any] | None,
    user_message: str,
    retrieval_context: str = "",
    platform_knowledge: str = "",
    skill_catalog: str = "",
    activated_skills: str = "",
    runtime_context: str = "",
    memory_context: str = "",
    context_instruction: str = "",
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    """构建受预算约束的多轮对话 messages（system + history + user）。"""
    limits = get_prompt_limits(settings)
    user = truncate_to_budget(user_message.strip(), limits["user_max_chars"])

    history_tail = trim_chat_history(
        history,
        max_messages=limits["history_max_messages"],
        max_chars=limits["history_max_chars"],
    )

    extras: list[str] = []
    if runtime_context.strip():
        extras.append(runtime_context.strip())
    if skill_catalog.strip():
        extras.append(skill_catalog.strip())
    if activated_skills.strip():
        extras.append(activated_skills.strip())
    if memory_context.strip():
        extras.append(memory_context.strip())
    if platform_knowledge.strip():
        extras.append(f"【平台操作知识库】\n{platform_knowledge.strip()}")
    if retrieval_context.strip():
        instruction = (context_instruction or "").strip()
        body = retrieval_context.strip()
        extras.append(f"{instruction}\n\n{body}" if instruction else body)

    combined_extra = truncate_to_budget(
        "\n\n".join(part for part in extras if part),
        limits["context_max_chars"],
    )

    full_system = system.strip()
    if combined_extra:
        full_system = f"{full_system}\n\n{combined_extra}"

    messages: list[dict[str, str]] = [{"role": "system", "content": full_system}]
    for item in history_tail:
        role = item.role if hasattr(item, "role") else str(item.get("role", "user"))
        content = item.content if hasattr(item, "content") else str(item.get("content") or "")
        messages.append({"role": str(role), "content": str(content).strip()})
    messages.append({"role": "user", "content": user})

    return fit_messages_to_total_budget(messages, limits["prompt_max_chars"])


def build_bounded_qa_messages(
    *,
    system: str,
    question: str,
    context: str,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    limits = get_prompt_limits(settings)
    q = truncate_to_budget(question.strip(), limits["user_max_chars"])
    ctx = truncate_to_budget(context.strip(), limits["context_max_chars"])
    user_content = f"问题：{q}\n\n检索片段：\n{ctx}"
    messages = [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user_content},
    ]
    return fit_messages_to_total_budget(messages, limits["prompt_max_chars"])


def llm_completion_extras(
    settings: Settings | None = None,
    *,
    unlimited: bool = False,
) -> dict[str, int]:
    """返回写入 LLM payload 的额外字段；默认不限制输出长度。"""
    if unlimited:
        return {}
    limits = get_prompt_limits(settings)
    cap = limits["max_output_tokens"]
    if cap <= 0:
        return {}
    return {"max_tokens": cap}
