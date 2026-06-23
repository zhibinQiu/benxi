"""Agent 工具循环上下文管理 — 压缩 tool 输出、集中注入检索材料。"""

from __future__ import annotations

import json
from typing import Any

from app.core.prompt_budget import fit_messages_to_total_budget, get_prompt_limits, truncate_to_budget
from app.core.text_utils import truncate_text

_LARGE_DATA_KEYS = frozenset(
    {
        "screenshot_base64",
        "html",
        "snapshot",
        "raw_html",
        "page_content",
        "markdown",
    }
)
_CONTEXT_KEYS = frozenset({"context", "context_text"})
_LIST_PREVIEW_KEYS = frozenset({"hits", "items", "refs", "citations", "rows"})


def compress_tool_result_for_loop(
    raw: str,
    *,
    max_chars: int = 2800,
    context_preview_chars: int = 900,
) -> str:
    """将 tool JSON 压缩为要点：summary + 计数 + 短预览，避免撑爆 prompt。"""
    text = (raw or "").strip()
    if not text:
        return text
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return truncate_text(text, max_chars)

    if not isinstance(body, dict):
        return truncate_text(text, max_chars)

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

    if isinstance(compact_data, dict) and compact_data.get("context_preview"):
        compact_data["context_preview"] = truncate_text(
            str(compact_data["context_preview"]),
            max(200, max_chars // 3),
        )
        compact["data"] = compact_data
        out = json.dumps(compact, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    if summary:
        return json.dumps(
            {"ok": body.get("ok"), "summary": truncate_text(summary, max_chars - 80)},
            ensure_ascii=False,
        )
    return truncate_text(out, max_chars)


def _compact_tool_data(
    data: Any,
    *,
    context_preview_chars: int,
) -> Any:
    if data is None:
        return None
    if not isinstance(data, dict):
        s = str(data)
        return s if len(s) <= 800 else truncate_text(s, 800)

    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in _LARGE_DATA_KEYS:
            continue
        if key in _CONTEXT_KEYS:
            text = str(value or "").strip()
            if text:
                preview = text.replace("\n", " ")
                out["context_preview"] = truncate_text(preview, context_preview_chars)
                out["context_chars"] = len(text)
            continue
        if key in _LIST_PREVIEW_KEYS and isinstance(value, list):
            out[f"{key}_count"] = len(value)
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
                        snippets.append(truncate_text(snip, 120))
                if snippets:
                    out["snippet_preview"] = " | ".join(snippets)
            continue
        if isinstance(value, str) and len(value) > 1200:
            out[key] = truncate_text(value, 1200)
        elif isinstance(value, (dict, list)):
            serialized = json.dumps(value, ensure_ascii=False)
            if len(serialized) > 1200:
                out[key] = truncate_text(serialized, 1200)
            else:
                out[key] = value
        else:
            out[key] = value
    return out or None


def append_retrieval_context(loop_state: dict[str, Any] | None, context: str) -> None:
    """将检索片段写入 loop_state，供 system 层集中注入（tool 消息不再重复全文）。"""
    if loop_state is None:
        return
    block = (context or "").strip()
    if not block:
        return
    parts: list[str] = list(loop_state.get("retrieval_context_parts") or [])
    parts.append(block)
    limits = get_prompt_limits()
    combined = "\n\n".join(parts)
    if len(combined) > limits["context_max_chars"]:
        combined = truncate_to_budget(combined, limits["context_max_chars"])
        parts = [combined]
    loop_state["retrieval_context_parts"] = parts


def build_retrieval_context_block(loop_state: dict[str, Any] | None) -> str:
    parts = list((loop_state or {}).get("retrieval_context_parts") or [])
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return (
        "【已检索材料】以下编号 [n] 可直接用于回答引用；"
        "勿重复调用相同检索。\n\n"
        f"{body}"
    )


def inject_retrieval_context_message(
    messages: list[dict[str, Any]],
    loop_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """用最新检索块替换/追加 system 消息，避免 tool 历史重复携带全文。"""
    block = build_retrieval_context_block(loop_state)
    if not block:
        return messages

    marker = "【已检索材料】"
    out = [dict(m) for m in messages]
    for idx, msg in enumerate(out):
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        if marker in content:
            head = content.split(marker, 1)[0].rstrip()
            out[idx]["content"] = f"{head}\n\n{block}".strip() if head else block
            return out

    out.append({"role": "system", "content": block})
    return out


def trim_agent_loop_messages(
    messages: list[dict[str, Any]],
    *,
    max_total_chars: int | None = None,
    keep_full_tool_results: int = 1,
) -> list[dict[str, Any]]:
    """裁剪 agent 循环 messages：旧 tool 只留 summary，总长度受 prompt 预算约束。"""
    budget = max_total_chars or get_prompt_limits()["prompt_max_chars"]
    rows = [dict(m) for m in messages]

    tool_indices = [i for i, m in enumerate(rows) if m.get("role") == "tool"]
    for idx in tool_indices[:-keep_full_tool_results]:
        rows[idx]["content"] = compress_tool_result_for_loop(
            str(rows[idx].get("content") or ""),
            max_chars=420,
            context_preview_chars=0,
        )

    return fit_messages_to_total_budget(rows, budget)
