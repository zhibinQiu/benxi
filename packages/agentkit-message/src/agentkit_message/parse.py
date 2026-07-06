"""LLM 正文中内嵌工具调用的提取与归一化。

许多 LLM（如 DeepSeek）会在 ``content`` 字符串中以 DSML 等非标准格式
嵌入工具调用而非走 API ``tool_calls``。本模块负责：
1. 检测并提取这些内嵌工具调用
2. 剥离工具标记，保留剩余正文
3. 流式场景下实时过滤
"""

from __future__ import annotations

import re
import uuid
from typing import Any

# ── DSML 标记正则 ────────────────────────────────────────────────────────────

# 竖线字符（半角 | 和全角 ｜）
_DSML_PIPE_CHARS = "\uff5c|"
# 匹配 DSML 定界符标签，如 <|DSML|>、<｜DSML｜>、<|DSMLinvoke>
_DELIM_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1(?P<suffix>\w*)(?:\s[^>]*)?>",
    re.UNICODE,
)
# 匹配 <|DSML|>invoke name="xxx">...</|DSML|>invoke>
_INVOKE_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1invoke name=\"([^\"]+)\""
    + r"[^>]*>"
    + r"(.*?)"
    + r"</\1DSML\1invoke>",
    re.DOTALL | re.UNICODE,
)
# 匹配 <|DSML|>parameter name="xxx">value</|DSML|>parameter>
_PARAM_RE = re.compile(
    r"<([" + re.escape(_DSML_PIPE_CHARS) + r"]+)DSML\1parameter name=\"([^\"]+)\""
    + r"(?:\s+string=\"(?:true|false)\")?"
    + r"[^>]*>"
    + r"(.*?)"
    + r"</\1DSML\1parameter>",
    re.DOTALL | re.UNICODE,
)


def content_has_tool_markup(text: str) -> bool:
    """检查正文中是否包含 DSML 等工具调用标记。"""
    return bool(_DELIM_RE.search(text or ""))


def _parse_dsml_invoke(name: str, body: str) -> dict[str, Any] | None:
    """解析单个 DSML invoke 块为 API 兼容的 tool_call dict。"""
    args: dict[str, Any] = {}
    for match in _PARAM_RE.finditer(body):
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
            "arguments": _serialize_args(args),
        },
    }


def _serialize_args(args: dict[str, Any]) -> str:
    """将参数字典序列化为 JSON 字符串，兼容 LLM 可能在值中嵌入 JSON 的情况。

    尝试对每个值进行 JSON 解析以支持嵌套结构，fallback 到原字符串。
    """
    import json

    result: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str):
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                result[k] = v
        else:
            result[k] = v
    return json.dumps(result, ensure_ascii=False)


def _strip_dsml_blocks(text: str) -> str:
    """移除正文中全部 DSML 块（含未闭合尾部）。"""
    cleaned = text or ""
    while True:
        match = _DELIM_RE.search(cleaned)
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
        cleaned = cleaned[:start] + cleaned[end + len(close):]
    # 清理任何残留的 DSML 结束标签
    cleaned = _DELIM_RE.sub("", cleaned)
    cleaned = re.sub(
        r"</[" + re.escape(_DSML_PIPE_CHARS) + r"]+DSML[" + re.escape(_DSML_PIPE_CHARS) + r"]+\w*>",
        "",
        cleaned,
        flags=re.UNICODE,
    )
    return cleaned.strip()


def extract_embedded_tool_calls(
    content: str,
) -> tuple[str, list[dict[str, Any]]]:
    """从 LLM 正文中提取所有 DSML 内嵌工具调用。

    Args:
        content: LLM 返回的 ``content`` 字符串。
    Returns:
        (clean_text, tool_calls)：
        - clean_text: 剥离所有 DSML 标记后的剩余正文。
        - tool_calls: 与 API ``tool_calls`` 格式兼容的 dict 列表。
          每个包含 ``id``、``type``、``function``（含 ``name``、``arguments``）。
    """
    text = content or ""
    if not content_has_tool_markup(text):
        return text.strip(), []

    tool_calls: list[dict[str, Any]] = []
    for match in _INVOKE_RE.finditer(text):
        parsed = _parse_dsml_invoke(match.group(2), match.group(3))
        if parsed:
            tool_calls.append(parsed)

    return _strip_dsml_blocks(text), tool_calls


def strip_tool_markup(text: str) -> str:
    """剥离所有工具调用标记，仅保留面向用户的正文。"""
    stripped, _ = extract_embedded_tool_calls(text or "")
    return stripped


def normalize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """将正文内嵌的工具调用提升到 ``message.tool_calls``。

    兼容标准 API 格式：返回的 message 中 ``tool_calls`` 字段包含全部调用
    （既有 API 平台生成的，也有从正文提取的）。

    Args:
        message: LLM 返回的 assistant message dict。
    Returns:
        归一化后的 message dict。
    """
    out = dict(message)
    existing = list(out.get("tool_calls") or [])
    content = str(out.get("content") or "")
    stripped, embedded = extract_embedded_tool_calls(content)
    if embedded:
        out["tool_calls"] = existing + embedded
        out["content"] = stripped
    elif content_has_tool_markup(content):
        out["content"] = stripped
    return out


class DsmlStreamFilter:
    """流式输出场景下实时过滤 DSML 工具标记。

    用法：:

        filter = DsmlStreamFilter()
        for chunk in llm_stream:
            clean = filter.feed(chunk)
            if clean:
                yield clean
        yield filter.flush()
    """

    _TAIL_HOLD = 80

    def __init__(self) -> None:
        self._raw = ""
        self._emitted_len = 0

    @property
    def raw_text(self) -> str:
        """累积的未处理原始文本。"""
        return self._raw

    def feed(self, chunk: str) -> str:
        """写入一个流式 chunk，返回本次可安全显示的纯文本（可能为空）。"""
        if not chunk:
            return ""
        self._raw += chunk
        clean = strip_tool_markup(self._raw)
        committed = clean
        if len(clean) > self._TAIL_HOLD:
            committed = clean[: -self._TAIL_HOLD]
        if len(committed) <= self._emitted_len:
            return ""
        out = committed[self._emitted_len:]
        self._emitted_len = len(committed)
        return out

    def flush(self) -> str:
        """返回剩余待提交文本并重置状态。"""
        clean = strip_tool_markup(self._raw)
        if len(clean) <= self._emitted_len:
            self._raw = ""
            self._emitted_len = 0
            return ""
        out = clean[self._emitted_len:]
        self._raw = ""
        self._emitted_len = 0
        return out
