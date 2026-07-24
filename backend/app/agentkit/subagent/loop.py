"""子 Agent LLM + tool 隔离循环。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app.agentkit.subagent.types import LlmCompletionFn, SubagentKindConfig, ToolExecuteFn, ToolRecordFn

_logger = logging.getLogger(__name__)

# 仅承诺将检索/调用工具、尚未给出事实结论的中间话术
_PROMISE_ONLY_RE = re.compile(
    r"(?:我会|我将|我先|接下来|正在|准备|开始).{0,12}(?:搜索|检索|查询|调用|并行)"
    r"|(?:先|马上|立刻).{0,8}(?:搜索|检索|查询)"
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
) -> str:
    """运行隔离 tool 循环，返回摘要文本。"""
    _norm = normalize_message or (lambda m: m if isinstance(m, dict) else {})
    _strip = strip_markup or (lambda t: t)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": kind_config.system_contract},
        {
            "role": "user",
            "content": (
                f"【子任务】\n{task[:6000]}\n\n"
                "要求：需要事实时必须先发起 tool_calls；"
                "工具返回后基于结果给出完整中文结论与来源，禁止只说「我会搜索」。"
            ),
        },
    ]
    final_summary = ""
    tools_ran = False

    for round_idx in range(kind_config.max_rounds):
        from app.core.stream_cancel import raise_if_stream_cancelled

        raise_if_stream_cancelled()
        try:
            from app.core.stream_cancel import await_unless_cancelled

            choice = await await_unless_cancelled(
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
            # 同轮「我会先搜索」文案不得当作结论；必须执行工具后再作答
            messages.append(message)
            for tc in tool_calls:
                raise_if_stream_cancelled()
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                tool_name = str(fn.get("name") or "")
                tool_id = str(tc.get("id") or uuid.uuid4())
                raw_args = fn.get("arguments") or "{}"
                result_text = await await_unless_cancelled(
                    execute_tool(tool_name, raw_args),
                    poll_sec=0.25,
                )
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
            # 继续下一轮：基于工具结果写结论
            continue

        if content and not _is_promise_only_summary(content):
            final_summary = content
            break
        if content and _is_promise_only_summary(content) and not tools_ran:
            # 空口承诺且未调工具：强制再试一轮，并提醒必须 tool_calls
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "禁止只描述计划。请立刻调用 web_search / run_tool_batch / "
                        "knowledge_retrieve / kg_query 等工具获取真实材料，"
                        "然后再给出中文结论。"
                    ),
                }
            )
            continue
        if content:
            # 有工具后仍是空话：用证据兜底
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
                or "子 Agent 已调用工具但未产出可读结论"
            )
        else:
            final_summary = "子 Agent 未调用工具，未产出有效摘要"
    return final_summary[:8000]
