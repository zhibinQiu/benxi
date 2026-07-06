"""智能体运行时状态 — 进程内追踪活跃 tool loop（Phase 2 接入执行层）。"""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_active: dict[str, set[str]] = defaultdict(set)


def mark_agent_running(agent_id: str, conversation_id: str) -> None:
    agent = (agent_id or "").strip()
    conv = (conversation_id or "").strip()
    if not agent or not conv:
        return
    with _lock:
        _active[agent].add(conv)


def mark_agent_idle(agent_id: str, conversation_id: str) -> None:
    agent = (agent_id or "").strip()
    conv = (conversation_id or "").strip()
    if not agent or not conv:
        return
    with _lock:
        bucket = _active.get(agent)
        if not bucket:
            return
        bucket.discard(conv)
        if not bucket:
            del _active[agent]


def agent_runtime_status(agent_id: str) -> tuple[str, int]:
    agent = (agent_id or "").strip()
    with _lock:
        count = len(_active.get(agent, set()))
    if count > 0:
        return "running", count
    return "idle", 0


def reset_agent_runtime_state() -> None:
    with _lock:
        _active.clear()
