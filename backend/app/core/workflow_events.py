"""Workflow SSE 事件构造（多服务共用）。

提供了两套 API：
- ``workflow_event()`` / ``workflow_event_json()`` — 构造 workflow 事件 dict/JSON
- ``sse_*()`` 函数 — 构造 SSE 标准 payload（delta / attachment / done / error / replace）
"""

from __future__ import annotations

import json
from typing import Any

_step_seq_by_prefix: dict[str, int] = {}


def reset_workflow_step_seq(prefix: str) -> None:
    _step_seq_by_prefix[prefix] = 0


def next_workflow_step_id(prefix: str = "step") -> str:
    n = _step_seq_by_prefix.get(prefix, 0) + 1
    _step_seq_by_prefix[prefix] = n
    return f"{prefix}{n}"


def workflow_event(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
    **extra: Any,
) -> dict[str, Any]:
    ev: dict[str, Any] = {"phase": phase, "title": title, "status": status}
    if detail:
        ev["detail"] = detail
    if tool:
        ev["tool"] = tool
    if step_id:
        ev["step_id"] = step_id
    ev.update(extra)
    return ev


def workflow_event_json(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
    **extra: Any,
) -> str:
    return json.dumps(
        {"workflow": workflow_event(phase, title=title, detail=detail, tool=tool, status=status, step_id=step_id, **extra)},
        ensure_ascii=False,
    )


# ── SSE 标准 Payload 构造 ───────────────────────


def sse_delta(text: str) -> str:
    """LLM 回复增量文本。"""
    return json.dumps({"delta": text}, ensure_ascii=False)


def sse_workflow(data: dict[str, Any]) -> str:
    """Workflow 阶段事件。"""
    return json.dumps({"workflow": data}, ensure_ascii=False)


def sse_attachment(data: dict[str, Any]) -> str:
    """附件。"""
    return json.dumps({"attachments": [data]}, ensure_ascii=False)


def sse_done(**extra: Any) -> str:
    """执行完毕。"""
    return json.dumps({"done": True, **extra}, ensure_ascii=False)


def sse_error(message: str) -> str:
    """错误。"""
    return json.dumps({"error": message}, ensure_ascii=False)


def sse_replace(text: str) -> str:
    """替换 LLM 回复（用于 synth 覆盖）。"""
    return json.dumps({"replace": text}, ensure_ascii=False)


def sse_citations(citations: list[dict[str, Any]]) -> str:
    """引用列表。"""
    return json.dumps({"citations": citations}, ensure_ascii=False)


def sse_follow_up(questions: list[str]) -> str:
    """跟进问题。"""
    return json.dumps({"follow_up_questions": questions}, ensure_ascii=False)


def sse_conversation_id(conv_id: str) -> str:
    """会话 ID。"""
    return json.dumps({"conversation_id": conv_id}, ensure_ascii=False)
