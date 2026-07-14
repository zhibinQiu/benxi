"""工具 JSON 结果压缩 — 控制 prompt 预算，避免撑爆上下文窗口。"""

from __future__ import annotations

import json
from typing import Any

# 常见大字段名（base64 图片、HTML 原文等）
_LARGE_DATA_KEYS: frozenset[str] = frozenset({
    "screenshot_base64",
    "screenshot_url",
    "storage_key",
    "html",
    "snapshot",
    "raw_html",
    "page_content",
    "markdown",
})

# 长文本上下文 key
_CONTEXT_KEYS: frozenset[str] = frozenset({"context", "context_text"})

# 列表预览 key
_LIST_PREVIEW_KEYS: frozenset[str] = frozenset({
    "hits", "items", "refs", "citations", "rows",
})


def _truncate(text: str, max_chars: int, *, suffix: str = "…") -> str:
    """安全截断字符串。"""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + suffix


def _compact_tool_data(
    data: Any,
    *,
    context_preview_chars: int = 900,
    max_field_chars: int = 800,
    max_list_serialized: int = 1200,
) -> Any:
    """递归压缩 tool data 子字段。"""
    if data is None:
        return None
    if not isinstance(data, dict):
        s = str(data)
        return s if len(s) <= max_field_chars else _truncate(s, max_field_chars)

    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in _LARGE_DATA_KEYS:
            continue  # 跳过大型二进制/原始数据
        if key in _CONTEXT_KEYS:
            text = str(value or "").strip()
            if text:
                preview = text.replace("\n", " ")
                out["context_preview"] = _truncate(preview, context_preview_chars)
                out["context_chars"] = len(text)
            continue
        if key in _LIST_PREVIEW_KEYS and isinstance(value, list):
            out[f"{key}_count"] = len(value)
            # 对 hits 列表做 snippet 预览
            if value and key == "hits":
                snippets: list[str] = []
                for item in value[:2]:
                    if not isinstance(item, dict):
                        continue
                    snip = (
                        item.get("snippet")
                        or item.get("highlight")
                        or item.get("content")
                        or ""
                    )
                    snip = str(snip).strip().replace("\n", " ")
                    if snip:
                        snippets.append(_truncate(snip, 120))
                if snippets:
                    out["snippet_preview"] = " | ".join(snippets)
            continue
        if isinstance(value, str) and len(value) > max_list_serialized:
            out[key] = _truncate(value, max_list_serialized)
        elif isinstance(value, (dict, list)):
            serialized = json.dumps(value, ensure_ascii=False)
            if len(serialized) > max_list_serialized:
                out[key] = _truncate(serialized, max_list_serialized)
            else:
                out[key] = value
        else:
            out[key] = value
    return out or None


def compress_tool_result(
    raw: str,
    *,
    max_chars: int = 2800,
    context_preview_chars: int = 900,
) -> str:
    """将 tool JSON 字符串压缩为要点摘要。

    处理策略：
    1. 非 JSON → 直接截断
    2. JSON dict → 提取 ``summary`` + 保留 ``ok`` + 压缩 ``data``
    3. 仍超 max_chars → 逐级降级：先缩 context_preview，再缩 summary

    Args:
        raw: 工具返回的原始 JSON 字符串。
        max_chars: 压缩后最大字符数。
        context_preview_chars: 上下文预览字段最大字符数。
    Returns:
        压缩后的字符串。
    """
    text = (raw or "").strip()
    if not text:
        return text
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return _truncate(text, max_chars)

    if not isinstance(body, dict):
        return _truncate(text, max_chars)

    summary = str(body.get("summary") or "").strip()
    data = body.get("data")
    compact_data = _compact_tool_data(
        data,
        context_preview_chars=context_preview_chars,
    )
    compact: dict[str, Any] = {
        "ok": body.get("ok"),
        "summary": summary,
    }
    if compact_data is not None:
        compact["data"] = compact_data

    out = json.dumps(compact, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    # 二级压缩：截断 context_preview
    if isinstance(compact_data, dict) and compact_data.get("context_preview"):
        compact_data["context_preview"] = _truncate(
            str(compact_data["context_preview"]),
            max(200, max_chars // 3),
        )
        compact["data"] = compact_data
        out = json.dumps(compact, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    # 三级压缩：只保留 summary
    if summary:
        return json.dumps(
            {"ok": body.get("ok"), "summary": _truncate(summary, max_chars - 80)},
            ensure_ascii=False,
        )
    return _truncate(out, max_chars)
