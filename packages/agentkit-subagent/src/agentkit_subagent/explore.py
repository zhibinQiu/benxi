"""并行 explore — 多 query × 多 skill 步骤，无 LLM 子循环。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from agentkit_subagent.context import child_state_from_parent
from agentkit_subagent.types import ExploreSkillStep, SkillInvokeFn

_logger = logging.getLogger(__name__)


async def _explore_single_query(
    query: str,
    *,
    base_state: dict[str, Any],
    steps: tuple[ExploreSkillStep, ...],
    invoke_skill: SkillInvokeFn,
) -> tuple[str, dict[str, Any]]:
    child_state = dict(base_state)
    child_state["isolated_subagent"] = True
    tasks = [
        invoke_skill(child_state, step.skill_name, step.action, step.param_key, query)
        for step in steps
    ]
    parts = await asyncio.gather(*tasks, return_exceptions=True)
    lines: list[str] = []
    for part in parts:
        if isinstance(part, Exception):
            _logger.debug("explore step failed: %s", part)
            continue
        text = str(part or "").strip()
        if text:
            lines.append(text[:600])
    if not lines:
        summary = f"「{query[:80]}」未检索到有效材料"
    else:
        summary = f"【{query[:80]}】\n" + "\n".join(f"- {line}" for line in lines[:6])
    return summary, child_state


async def parallel_explore_queries(
    queries: list[str],
    *,
    loop_state: dict[str, Any] | None,
    agent_id: str,
    steps: tuple[ExploreSkillStep, ...],
    invoke_skill: SkillInvokeFn,
    append_retrieval: Any = None,
) -> tuple[str, dict[str, Any]]:
    """多 query 并行 explore，合并 child 观测。"""
    base_state = child_state_from_parent(loop_state, kind="explore", agent_id=agent_id)
    results = await asyncio.gather(
        *(
            _explore_single_query(
                query,
                base_state=base_state,
                steps=steps,
                invoke_skill=invoke_skill,
            )
            for query in queries
        ),
        return_exceptions=True,
    )
    merged_state: dict[str, Any] = dict(base_state)
    blocks: list[str] = []
    for item in results:
        if isinstance(item, Exception):
            _logger.warning("parallel explore query failed: %s", item)
            continue
        summary, child_state = item
        blocks.append(summary)
        for key in ("citations", "tool_outcome_lines", "retrieval_context_parts"):
            bucket = child_state.get(key)
            if isinstance(bucket, list) and bucket:
                merged_state.setdefault(key, []).extend(bucket)
        retrieval = str(child_state.get("retrieval_context") or "").strip()
        if retrieval and append_retrieval is not None:
            append_retrieval(merged_state, retrieval)

    combined = "\n\n".join(blocks).strip() or "并行探索未产出有效摘要"
    return combined[:4000], merged_state
