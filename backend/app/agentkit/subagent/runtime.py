"""子 Agent 统一入口 — explore 并行 / 单 query 隔离循环。"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop_state import LoopState

from app.agentkit.subagent.config import SubagentConfig
from app.agentkit.subagent.context import (
    child_state_from_parent,
    merge_child_into_parent,
    normalize_queries,
)
from app.agentkit.subagent.explore import parallel_explore_queries
from app.agentkit.subagent.loop import run_subagent_tool_loop


async def execute_subagent(
    *,
    config: SubagentConfig,
    kind: str,
    task: str = "",
    queries: list[str] | None = None,
    user_message: str = "",
    loop_state: LoopState | None = None,
    agent_id: str = "",
    llm_configured: bool = True,
) -> str:
    """执行子 Agent，返回 JSON 字符串（与平台 invoke_context_subagent 兼容）。

    使用 ``SubagentConfig`` 注入宿主依赖，替代原 13 个松散参数。
    """
    sub_kind = (kind or "").strip().lower()
    kind_config = config.runtime.kinds.get(sub_kind)
    if kind_config is None:
        return _result(False, f"未知 subagent kind: {sub_kind or '(empty)'}")
    if not llm_configured:
        return _result(False, "LLM 未配置")

    normalized = normalize_queries(
        task or user_message,
        queries,
        max_queries=config.runtime.max_parallel_queries,
    )
    if not normalized:
        return _result(False, "task 或 queries 不能为空")

    agent = agent_id or str((loop_state or {}).get("agent_id") or "")

    # 并行 explore 模式（多 query + 有 invoke_skill + 有 explore_steps）
    if (
        sub_kind == "explore"
        and len(normalized) >= config.runtime.parallel_explore_min_queries
        and config.invoke_skill is not None
        and config.runtime.explore_steps
    ):
        summary, child_state = await parallel_explore_queries(
            normalized,
            loop_state=loop_state,
            agent_id=agent,
            steps=config.runtime.explore_steps,
            invoke_skill=config.invoke_skill,
            append_retrieval=config.append_retrieval,
        )
        task_label = " | ".join(normalized[:3])
        merge_child_into_parent(
            loop_state,
            child_state,
            kind=sub_kind,
            task=task_label,
            summary=summary,
            append_retrieval=config.append_retrieval,
        )
        return _result(True, summary[:2000], {"kind": sub_kind, "parallel_queries": len(normalized), "mode": "parallel_retrieval"})

    # 隔离 tool loop 模式
    if config.execute_tool is None or config.record_tool is None or config.llm_complete is None or config.build_tool_specs is None:
        return _result(False, "子 Agent 运行时未配置")

    sub_task = normalized[0]
    child_state = child_state_from_parent(loop_state, kind=sub_kind, agent_id=agent)
    tool_specs = config.build_tool_specs(set(kind_config.allowed_tools))
    summary = await run_subagent_tool_loop(
        kind_config=kind_config,
        task=sub_task,
        child_state=child_state,
        tool_specs=tool_specs,
        llm_complete=config.llm_complete,
        execute_tool=config.execute_tool,
        record_tool=config.record_tool,
        normalize_message=config.normalize_message,
        strip_markup=config.strip_markup,
    )
    merge_child_into_parent(
        loop_state,
        child_state,
        kind=sub_kind,
        task=sub_task,
        summary=summary,
        append_retrieval=config.append_retrieval,
    )
    return _result(True, summary[:2000], {"kind": sub_kind, "mode": "isolated_loop"})


def _result(ok: bool, summary: str, data: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {"ok": ok, "summary": summary, "data": data} if data else {"ok": ok, "summary": summary},
        ensure_ascii=False,
    )
