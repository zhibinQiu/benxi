"""子 Agent LLM + tool 隔离循环。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from agentkit_subagent.types import LlmCompletionFn, SubagentKindConfig, ToolExecuteFn, ToolRecordFn

_logger = logging.getLogger(__name__)


def parse_tool_summary(raw: str) -> tuple[bool, str]:
    """解析 tool 返回 JSON 的 ok/summary 字段。"""
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return False, raw[:500]
    return bool(body.get("ok")), str(body.get("summary") or raw)[:800]


async def run_subagent_tool_loop(
    *,
    kind_config: SubagentKindConfig,
    task: str,
    child_state: dict[str, Any],
    tool_specs: list[dict[str, Any]],
    llm_complete: LlmCompletionFn,
    execute_tool: ToolExecuteFn,
    record_tool: ToolRecordFn,
    normalize_message: Any = None,
    strip_markup: Any = None,
) -> str:
    """运行隔离 tool 循环，返回摘要文本。"""
    _norm = normalize_message or (lambda m: m if isinstance(m, dict) else {})
    _strip = strip_markup or (lambda t: t)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": kind_config.system_contract},
        {"role": "user", "content": f"【子任务】\n{task[:1200]}"},
    ]
    final_summary = ""

    for round_idx in range(kind_config.max_rounds):
        try:
            choice = await llm_complete(messages, tool_specs or None)
        except Exception:
            _logger.exception("subagent LLM failed kind=%s round=%s", kind_config.kind, round_idx)
            break
        if not choice:
            break
        message = _norm(choice.get("message") or {})
        tool_calls = message.get("tool_calls") or []
        content = _strip(str(message.get("content") or "")).strip()
        if not tool_calls:
            final_summary = content or final_summary
            break
        messages.append(message)
        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            tool_name = str(fn.get("name") or "")
            tool_id = str(tc.get("id") or uuid.uuid4())
            raw_args = fn.get("arguments") or "{}"
            result_text = await execute_tool(tool_name, raw_args)
            ok, summary = parse_tool_summary(result_text)
            record_tool(
                child_state,
                tool_name,
                raw_args,
                result_text,
                summary,
                f"subagent-{kind_config.kind}-{uuid.uuid4().hex[:8]}",
            )
            messages.append(
                {"role": "tool", "tool_call_id": tool_id, "content": result_text[:4000]}
            )
            if content:
                final_summary = content

    if not final_summary:
        outcomes = list(child_state.get("tool_outcome_lines") or [])
        final_summary = "\n".join(str(x) for x in outcomes[-4:]) or "子 Agent 未产出有效摘要"
    return final_summary[:2000]
