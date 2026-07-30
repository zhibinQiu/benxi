"""子 Agent LLM + tool 隔离循环。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent.subagent.types import LlmCompletionFn, SubagentKindConfig, ToolExecuteFn, ToolRecordFn

_logger = logging.getLogger(__name__)

CheckCancelledFn = Callable[[], None]
AwaitUnlessCancelledFn = Callable[..., Awaitable[Any]]

# Promise-only intermediate phrasing (ZH/EN)
_PROMISE_ONLY_RE = re.compile(
    r"(?:我会|我将|我先|接下来|正在|准备|开始).{0,12}(?:搜索|检索|查询|调用|并行)"
    r"|(?:先|马上|立刻).{0,8}(?:搜索|检索|查询)"
    r"|I(?:'ll| will| am going to).{0,20}(?:search|retriev|look up|query)"
    r"|tool_calls|run_tool_batch|web_search\s*\(",
    re.I,
)


def parse_tool_summary(raw: str) -> tuple[bool, str]:
    """解析 tool 返回 JSON 的 ok/summary 字段。"""
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return False, raw[:500]
    return bool(body.get("ok")), str(body.get("summary") or raw)[:800]


def _is_promise_only_summary(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) > 400:
        return False
    return bool(_PROMISE_ONLY_RE.search(t))


def _summary_from_child_evidence(child_state: dict[str, Any]) -> str:
    """工具已执行但模型未给出终稿时，用检索材料/工具结果拼摘要。"""
    parts: list[str] = []
    retrieval = list(child_state.get("retrieval_context_parts") or [])
    for chunk in retrieval[-3:]:
        text = str(chunk or "").strip()
        if text:
            parts.append(text[:2500])
    if not parts:
        for line in list(child_state.get("tool_outcome_lines") or [])[-6:]:
            text = str(line or "").strip()
            if text:
                parts.append(text[:400])
    if not parts:
        return ""
    return "\n\n".join(parts)[:8000]


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
    check_cancelled: CheckCancelledFn | None = None,
    await_unless_cancelled: AwaitUnlessCancelledFn | None = None,
) -> str:
    """运行隔离 tool 循环，返回摘要文本。

    Cancel hooks are host-injected; when omitted, the loop awaits directly.
    """
    _norm = normalize_message or (lambda m: m if isinstance(m, dict) else {})
    _strip = strip_markup or (lambda t: t)

    async def _await(coro, *, poll_sec: float = 0.2):
        if await_unless_cancelled is not None:
            return await await_unless_cancelled(coro, poll_sec=poll_sec)
        return await coro

    def _check() -> None:
        if check_cancelled is not None:
            check_cancelled()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": kind_config.system_contract},
        {
            "role": "user",
            "content": (
                f"[Subtask]\n{task[:6000]}\n\n"
                "When facts are needed, issue tool_calls first; "
                "then conclude from tool results with sources. Do not only promise to search."
            ),
        },
    ]
    final_summary = ""
    tools_ran = False

    for round_idx in range(kind_config.max_rounds):
        _check()
        try:
            choice = await _await(
                llm_complete(messages, tool_specs or None),
                poll_sec=0.2,
            )
        except Exception:
            _logger.exception("subagent LLM failed kind=%s round=%s", kind_config.kind, round_idx)
            break
        if not choice:
            break
        message = _norm(choice.get("message") or {})
        tool_calls = message.get("tool_calls") or []
        content = _strip(str(message.get("content") or "")).strip()

        if tool_calls:
            tools_ran = True
            messages.append(message)
            for tc in tool_calls:
                _check()
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                tool_name = str(fn.get("name") or "")
                tool_id = str(tc.get("id") or uuid.uuid4())
                raw_args = fn.get("arguments") or "{}"
                result_text = await _await(
                    execute_tool(tool_name, raw_args),
                    poll_sec=0.25,
                )
                _ok, summary = parse_tool_summary(result_text)
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
            continue

        if content and not _is_promise_only_summary(content):
            final_summary = content
            break
        if content and _is_promise_only_summary(content) and not tools_ran:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Do not only describe a plan. Immediately call tools via tool_calls "
                        "(e.g. web_search / run_tool_batch / knowledge retrieve), "
                        "then conclude from real results."
                    ),
                }
            )
            continue
        if content:
            break
        break

    if not final_summary or _is_promise_only_summary(final_summary):
        evidence = _summary_from_child_evidence(child_state)
        if evidence:
            final_summary = evidence
        elif tools_ran:
            outcomes = list(child_state.get("tool_outcome_lines") or [])
            final_summary = (
                "\n".join(str(x) for x in outcomes[-4:])
                or "Subagent ran tools but produced no readable conclusion"
            )
        else:
            final_summary = "Subagent did not call tools; no usable summary"
    return final_summary[:8000]
