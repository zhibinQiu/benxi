"""子 Agent loop_state 上下文工具。"""

from __future__ import annotations

from typing import Any, Callable

from app.agentkit.loop.state import LoopState


def normalize_queries(
    task: str,
    queries: list[str] | None,
    *,
    max_queries: int = 4,
    min_query_len: int = 2,
    max_query_len: int = 500,
) -> list[str]:
    """去重并截断 query 列表；无 queries 时回退 task。"""
    out: list[str] = []
    seen: set[str] = set()
    for raw in queries or []:
        q = str(raw or "").strip()
        if len(q) < min_query_len or q in seen:
            continue
        seen.add(q)
        out.append(q[:max_query_len])
        if len(out) >= max_queries:
            break
    if out:
        return out
    task_text = (task or "").strip()
    return [task_text[:max_query_len]] if task_text else []


def child_state_from_parent(
    loop_state: LoopState | None,
    *,
    kind: str,
    agent_id: str,
) -> dict[str, Any]:
    """从父 loop_state 派生隔离子 state。"""
    child: dict[str, Any] = {
        "agent_id": (agent_id or "").strip() or None,
        "isolated_subagent": True,
        "subagent_kind": kind,
    }
    if loop_state is None:
        return child
    allowed_skills = loop_state.get("allowed_skill_names")
    if allowed_skills:
        child["allowed_skill_names"] = set(allowed_skills)
    parent_agent = str(loop_state.get("agent_id") or "").strip()
    if parent_agent:
        child["agent_id"] = parent_agent
    return child


def merge_child_into_parent(
    parent_loop_state: LoopState | None,
    child_loop_state: LoopState,
    *,
    kind: str,
    task: str,
    summary: str,
    append_retrieval: Callable[[dict[str, Any], str], None] | None = None,
) -> None:
    """将子 Agent 摘要与观测合并回父 loop_state。"""
    if parent_loop_state is None:
        return
    parent_loop_state.setdefault("subagent_summaries", []).append(
        {"kind": kind, "task": task[:400], "summary": summary[:2000]}
    )
    for key in ("citations", "tool_outcome_lines", "retrieval_context_parts"):
        bucket = child_loop_state.get(key)
        if isinstance(bucket, list) and bucket:
            parent_loop_state.setdefault(key, []).extend(bucket)
    retrieval = str(child_loop_state.get("retrieval_context") or "").strip()
    if retrieval and append_retrieval is not None:
        append_retrieval(parent_loop_state, retrieval)
