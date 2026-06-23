"""Workflow SSE 事件构造（多服务共用）。"""

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
) -> dict[str, Any]:
    ev: dict[str, Any] = {"phase": phase, "title": title, "status": status}
    if detail:
        ev["detail"] = detail
    if tool:
        ev["tool"] = tool
    if step_id:
        ev["step_id"] = step_id
    return ev


def workflow_event_json(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
) -> str:
    return json.dumps(
        {
            "workflow": workflow_event(
                phase,
                title=title,
                detail=detail,
                tool=tool,
                status=status,
                step_id=step_id,
            )
        },
        ensure_ascii=False,
    )
