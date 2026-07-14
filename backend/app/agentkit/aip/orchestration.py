"""多 hop 编排辅助 — 引用合并、回复选取。"""

from __future__ import annotations

from typing import Any, Callable

from app.agentkit.aip.messaging import reply_text_from_complete

_CITATION_KEYS = ("url", "title", "snippet", "document_id", "source")


def merge_hop_citations(citation_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """合并多智能体 hop 的引用，按出现顺序去重。"""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citations in citation_lists:
        for raw in citations or []:
            if not isinstance(raw, dict):
                continue
            key = "|".join(str(raw.get(k) or "")[:120] for k in _CITATION_KEYS)
            if not key.strip("|") or key in seen:
                continue
            seen.add(key)
            merged.append(dict(raw))
    return merged


def best_reply_from_hops(
    hop_completes: list[dict[str, Any] | None],
    *,
    extract_reply: Callable[[dict[str, Any] | None], str] | None = None,
) -> str | None:
    """从多个 hop complete 事件中选取最佳回复（默认优先 AIP handoff）。"""
    fn = extract_reply or reply_text_from_complete
    for event in reversed(hop_completes):
        text = fn(event)
        if text:
            return text
    return None
