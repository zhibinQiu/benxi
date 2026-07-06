"""LLM 内容过滤 — 识别并移除内部调试输出、工具调用标记等非面向用户文本。"""

from __future__ import annotations

import re
from typing import Any

from agentkit_message.parse import content_has_tool_markup

# ── 常见内部模式 ──────────────────────────────────────────────────────────────

_INTERNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 行号引用
    re.compile(r"\bL\d+\s*行\b"),
    # 代码引用
    re.compile(r"re\.(?:search|DOTALL|compile)"),
    re.compile(r"`update_uploaded_skill_file`"),
    re.compile(r"`run_skill_script`"),
    re.compile(r"run_skill_script\s*[\(\'\"]"),
    re.compile(r"示例命令"),
    # 工具标记
    re.compile(r"<\｜tool▁calls▁begin\｜>|<\｜tool▁call▁begin\｜>"),
)

_MERMAID_FENCE_RE = re.compile(r"```(?:mermaid)?\s*\n[\s\S]*?```", re.I)


def looks_like_internal_content(text: str, *, min_hits: int = 2) -> bool:
    """判断正文是否主要是实现/调试过程，不宜直接展示给用户。

    Args:
        text: 待检测文本。
        min_hits: 判定为内部内容的最小模式匹配数（默认 2）。
    Returns:
        True 表示疑似内部内容。
    """
    body = (text or "").strip()
    if not body:
        return True
    if content_has_tool_markup(body):
        return True
    hits = sum(1 for pat in _INTERNAL_PATTERNS if pat.search(body))
    if hits >= min_hits:
        return True
    if hits >= 1 and len(body) < 600:
        return True
    return False


def has_mermaid_deliverable(text: str) -> bool:
    """正文是否包含可渲染的 Mermaid 图表围栏。"""
    return bool(_MERMAID_FENCE_RE.search(text or ""))


def assistant_content_is_deliverable(
    content: str,
    *,
    instruction_only_skill: bool = False,
) -> bool:
    """判断助手回复是否包含对用户可见的交付结果。

    Args:
        content: 助手回复正文。
        instruction_only_skill: 是否为指令型 Skill（指令型有更宽松的判定）。
    Returns:
        True 表示有可交付内容。
    """
    text = (content or "").strip()
    if not text:
        return False
    if content_has_tool_markup(text):
        return False
    if has_mermaid_deliverable(text):
        return True
    if instruction_only_skill and not looks_like_internal_content(text):
        return len(text) >= 24
    return False


def sanitize_agent_reply(
    text: str,
    *,
    extra_patterns: list[re.Pattern[str]] | None = None,
) -> str:
    """净化面向用户的回复：去除工具调用标记与常见调试语句。

    Args:
        text: 原始回复文本。
        extra_patterns: 额外需要移除的正则模式。
    Returns:
        净化后的文本（若全部为内部内容则返回空字符串）。
    """
    raw = text or ""
    from agentkit_message.parse import extract_embedded_tool_calls

    body, embedded = extract_embedded_tool_calls(raw)
    if embedded and (not body or len(body) < 800):
        return ""

    mermaid_blocks = _MERMAID_FENCE_RE.findall(body)

    # 移除所有代码围栏
    body = re.sub(r"```[\s\S]*?```", "", body).strip()

    # 移除内部模式
    all_patterns = list(_INTERNAL_PATTERNS)
    if extra_patterns:
        all_patterns.extend(extra_patterns)
    for pat in all_patterns:
        body = pat.sub("", body)

    # 压缩多余空行
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    if mermaid_blocks:
        parts = [p for p in [body, *mermaid_blocks] if p]
        body = "\n\n".join(parts).strip()

    if looks_like_internal_content(body) and not mermaid_blocks:
        return ""
    return body


class ContentFilter:
    """可配置的内容过滤器，支持自定义内部模式。"""

    def __init__(
        self,
        *,
        extra_internal_patterns: list[re.Pattern[str]] | None = None,
    ) -> None:
        self._extra_patterns = list(extra_internal_patterns or [])

    def is_internal(self, text: str) -> bool:
        """判断是否为内部内容。"""
        return looks_like_internal_content(text)

    def sanitize(self, text: str) -> str:
        """净化回复文本。"""
        return sanitize_agent_reply(text, extra_patterns=self._extra_patterns)

    def is_deliverable(
        self,
        content: str,
        *,
        instruction_only_skill: bool = False,
    ) -> bool:
        """判断是否有可交付内容。"""
        return assistant_content_is_deliverable(
            content,
            instruction_only_skill=instruction_only_skill,
        )
