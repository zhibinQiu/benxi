"""解析 LLM 正文中嵌入的工具调用，并净化面向用户的回复。

大部分逻辑委托给 ``agentkit-message``，本层保留平台特有的内部模式匹配。"""

from __future__ import annotations

import re
from typing import Any

from app.agentkit.message import (
    DsmlStreamFilter as _DsmlStreamFilter,
    content_has_tool_markup,
    extract_embedded_tool_calls as _extract_embedded_tool_calls,
    normalize_assistant_message as _normalize_assistant_message,
    sanitize_agent_reply as _sanitize_agent_reply,
    strip_tool_markup as _strip_tool_markup,
)

# ── DSML 兼容常量（供外部引用） ──────────────────────────────────────────────

_DSML_PIPE = "\uff5c"
_DSML_TAG = f"{_DSML_PIPE}{_DSML_PIPE}DSML{_DSML_PIPE}{_DSML_PIPE}"

# 平台特有内部模式（agentkit 通用模式 + 平台业务关键词）
_INTERNAL_PATTERNS = (
    re.compile(r"\bL\d+\s*行\b"),
    re.compile(r"re\.(?:search|DOTALL|compile)"),
    re.compile(r"`update_uploaded_skill_file`"),
    re.compile(r"`run_skill_script`"),
    re.compile(r"run_skill_script\s*[\(\'\"]"),
    re.compile(r"示例命令"),
)


def content_has_dsml_markup(text: str) -> bool:
    """正文是否含 DSML 式工具调用标记。"""
    return content_has_tool_markup(text)


def extract_embedded_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    """从正文中提取 DSML 工具调用，并返回剥离后的剩余文本。"""
    return _extract_embedded_tool_calls(content)


def strip_dsml_markup(text: str) -> str:
    """剥离 DSML 工具块，保留其余正文。"""
    return _strip_tool_markup(text)


class DsmlStreamFilter:
    """流式输出时过滤 DSML 工具标记，避免原样展示给用户。"""

    def __init__(self) -> None:
        self._inner = _DsmlStreamFilter()

    @property
    def raw_text(self) -> str:
        return self._inner.raw_text

    def feed(self, chunk: str) -> str:
        return self._inner.feed(chunk)

    def flush(self) -> str:
        return self._inner.flush()


def looks_like_internal_agent_content(text: str) -> bool:
    """正文是否主要为实现/调试过程，不宜直接展示给用户。"""
    body = (text or "").strip()
    if not body:
        return True
    if content_has_tool_markup(body):
        return True
    hits = sum(1 for pat in _INTERNAL_PATTERNS if pat.search(body))
    if hits >= 2:
        return True
    if hits >= 1 and len(body) < 600:
        return True
    if "ohlc" in body and "re.search" in body:
        return True
    return False


def has_mermaid_deliverable(text: str) -> bool:
    """正文是否包含可渲染的 Mermaid 图表围栏。"""
    from app.agentkit.message.filter import has_mermaid_deliverable as _check

    return _check(text)


def assistant_content_is_deliverable(
    content: str,
    *,
    instruction_only_skill: bool = False,
) -> bool:
    """指令型技能等场景：模型在正文中直接交付用户可见结果。"""
    text = (content or "").strip()
    if not text:
        return False
    if content_has_tool_markup(text):
        return False
    if has_mermaid_deliverable(text):
        return True
    if instruction_only_skill and not looks_like_internal_agent_content(text):
        return len(text) >= 24
    # 通用直接回答：substantial 长度 + 非内部内容 = 可交付
    if (
        len(text) >= 12
        and not content_has_tool_markup(text)
        and not looks_like_internal_agent_content(text)
    ):
        return True
    return False


def sanitize_agent_user_reply(text: str) -> str:
    """去除工具调用标记与常见调试语句，保留可展示正文。"""
    extra_patterns = list(_INTERNAL_PATTERNS)
    return _sanitize_agent_reply(text, extra_patterns=extra_patterns)


def normalize_llm_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """将正文内嵌的工具调用提升到 message.tool_calls。"""
    return _normalize_assistant_message(message)
