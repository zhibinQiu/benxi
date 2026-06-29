"""解析 LLM 正文中嵌入的工具调用，并净化面向用户的回复。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

# DeepSeek 等模型偶发在 content 中输出 DSML 式工具块（非 API tool_calls）
_DSML_PIPE_CHARS = "\uff5c|"
_DSML_DELIM_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1(?P<suffix>\w*)(?:\s[^>]*)?>",
    re.UNICODE,
)
_DSML_INVOKE_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1invoke name=\"([^\"]+)\""
    + r"[^>]*>"
    + r"(.*?)"
    + r"</\1DSML\1invoke>",
    re.DOTALL | re.UNICODE,
)
_DSML_PARAM_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1parameter name=\"([^\"]+)\""
    + r"(?:\s+string=\"(?:true|false)\")?"
    + r"[^>]*>"
    + r"(.*?)"
    + r"</\1DSML\1parameter>",
    re.DOTALL | re.UNICODE,
)
# 兼容旧测试与单 delimiter 常量
_DSML_PIPE = "\uff5c"
_DSML_TAG = f"{_DSML_PIPE}{_DSML_PIPE}DSML{_DSML_PIPE}{_DSML_PIPE}"
_MERMAID_FENCE_RE = re.compile(r"```(?:mermaid)?\s*\n[\s\S]*?```", re.I)

_INTERNAL_PATTERNS = (
    _DSML_DELIM_RE,
    re.compile(r"</[" + re.escape(_DSML_PIPE_CHARS) + r"]+DSML[" + re.escape(_DSML_PIPE_CHARS) + r"]+\w+>", re.UNICODE),
    re.compile(r"\bL\d+\s*行\b"),
    re.compile(r"re\.(?:search|DOTALL|compile)"),
    re.compile(r"`update_uploaded_skill_file`"),
    re.compile(r"`run_skill_script`"),
    re.compile(r"run_skill_script\s*[\(\'\"]"),
    re.compile(r"示例命令"),
    re.compile(r"<\｜tool▁calls▁begin\｜>|<\｜tool▁call▁begin\｜>"),
)


def content_has_dsml_markup(text: str) -> bool:
    """正文是否含 DSML 式工具调用标记。"""
    return bool(_DSML_DELIM_RE.search(text or ""))


def _parse_dsml_invoke(name: str, body: str) -> dict[str, Any] | None:
    args: dict[str, Any] = {}
    for match in _DSML_PARAM_RE.finditer(body):
        key = match.group(2).strip()
        value = match.group(3)
        if key:
            args[key] = value
    if not name.strip():
        return None
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": name.strip(),
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def _strip_dsml_blocks(text: str) -> str:
    """移除正文中全部 DSML 块（含未闭合尾部）。"""
    cleaned = text or ""
    while True:
        match = _DSML_DELIM_RE.search(cleaned)
        if not match:
            break
        start = match.start()
        delim = match.group(1)
        suffix = match.group(2) or ""
        close = f"</{delim}DSML{delim}{suffix}>"
        end = cleaned.find(close, match.end())
        if end < 0:
            cleaned = cleaned[:start]
            break
        cleaned = cleaned[:start] + cleaned[end + len(close) :]
    cleaned = _DSML_DELIM_RE.sub("", cleaned)
    cleaned = re.sub(
        r"</[" + re.escape(_DSML_PIPE_CHARS) + r"]+DSML[" + re.escape(_DSML_PIPE_CHARS) + r"]+\w*>",
        "",
        cleaned,
        flags=re.UNICODE,
    )
    return cleaned.strip()


def extract_embedded_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    """从正文中提取 DSML 工具调用，并返回剥离后的剩余文本。"""
    text = content or ""
    if not content_has_dsml_markup(text):
        return text.strip(), []

    tool_calls: list[dict[str, Any]] = []
    for match in _DSML_INVOKE_RE.finditer(text):
        parsed = _parse_dsml_invoke(match.group(2), match.group(3))
        if parsed:
            tool_calls.append(parsed)

    return _strip_dsml_blocks(text), tool_calls


def strip_dsml_markup(text: str) -> str:
    """剥离 DSML 工具块，保留其余正文。"""
    stripped, _ = extract_embedded_tool_calls(text or "")
    return stripped


class DsmlStreamFilter:
    """流式输出时过滤 DSML 工具标记，避免原样展示给用户。"""

    _TAIL_HOLD = 80

    def __init__(self) -> None:
        self._raw = ""
        self._emitted_len = 0

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._raw += chunk
        clean = strip_dsml_markup(self._raw)
        committed = clean
        if len(clean) > self._TAIL_HOLD:
            committed = clean[: -self._TAIL_HOLD]
        if len(committed) <= self._emitted_len:
            return ""
        out = committed[self._emitted_len :]
        self._emitted_len = len(committed)
        return out

    def flush(self) -> str:
        clean = strip_dsml_markup(self._raw)
        if len(clean) <= self._emitted_len:
            self._raw = ""
            self._emitted_len = 0
            return ""
        out = clean[self._emitted_len :]
        self._raw = ""
        self._emitted_len = 0
        return out


def looks_like_internal_agent_content(text: str) -> bool:
    """正文是否主要为实现/调试过程，不宜直接展示给用户。"""
    body = (text or "").strip()
    if not body:
        return True
    if content_has_dsml_markup(body):
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
    return bool(_MERMAID_FENCE_RE.search(text or ""))


def assistant_content_is_deliverable(
    content: str,
    *,
    instruction_only_skill: bool = False,
) -> bool:
    """指令型技能等场景：模型在正文中直接交付用户可见结果。"""
    text = (content or "").strip()
    if not text:
        return False
    if content_has_dsml_markup(text):
        return False
    if has_mermaid_deliverable(text):
        return True
    if instruction_only_skill and not looks_like_internal_agent_content(text):
        return len(text) >= 24
    return False


def sanitize_agent_user_reply(text: str) -> str:
    """去除工具调用标记与常见调试语句，保留可展示正文。"""
    raw = text or ""
    body, embedded = extract_embedded_tool_calls(raw)
    if embedded and (not body or len(body) < 800):
        return ""
    mermaid_blocks = _MERMAID_FENCE_RE.findall(body)
    body = re.sub(r"```[\s\S]*?```", "", body).strip()
    for pat in _INTERNAL_PATTERNS:
        body = pat.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if mermaid_blocks:
        parts = [p for p in [body, *mermaid_blocks] if p]
        body = "\n\n".join(parts).strip()
    if looks_like_internal_agent_content(body) and not mermaid_blocks:
        return ""
    return body


def normalize_llm_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """将正文内嵌的工具调用提升到 message.tool_calls。"""
    out = dict(message)
    existing = list(out.get("tool_calls") or [])
    content = str(out.get("content") or "")
    stripped, embedded = extract_embedded_tool_calls(content)
    if embedded:
        out["tool_calls"] = existing + embedded
        out["content"] = stripped
    elif content_has_dsml_markup(content):
        out["content"] = stripped
    return out
