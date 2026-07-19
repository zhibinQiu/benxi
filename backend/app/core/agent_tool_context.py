"""Agent 工具循环上下文管理 — 压缩 tool 输出、检索材料注入、指纹去重。

职责：
  1. Tool 结果压缩（控制 prompt 预算）
  2. 检索/调研/修复上下文注入到 system 消息
  3. 工具调用指纹去重（相同调用不再重复执行）
  4. 历史消息裁剪（预算约束）
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from app.core.agent_loop_state import LoopState

from app.agentkit.tools.compress import compress_tool_result as _compress_tool_result
from app.core.prompt_budget import fit_messages_to_total_budget, get_prompt_limits, truncate_to_budget

# ── 常量 ──────────────────────────────────────────────────────────────────────

_MAX_SKILL_EXPLORE_CHARS: Final[int] = 2400
_MAX_SKILL_REPAIR_RECORDS: Final[int] = 4
_MAX_TOOL_RECORDS: Final[int] = 16
_MAX_CONCLUSION_CHARS: Final[int] = 4000

_TURN_TOOLS_MARKER: Final[str] = "【本轮对话已执行工具】"
_RETRIEVAL_MARKER: Final[str] = "【已检索材料】"
_SKILL_EXPLORE_MARKER: Final[str] = "【Skill 编写调研材料"
_REPAIR_MARKER: Final[str] = "【Skill 修复"
_TURN_MARKERS: Final[tuple[str, ...]] = (
    _TURN_TOOLS_MARKER, _RETRIEVAL_MARKER, _SKILL_EXPLORE_MARKER, _REPAIR_MARKER,
)
_SKILL_EXPLORE_HEADER: Final[str] = (
    "【Skill 编写调研材料 · 创建前必读】\n"
    "Below is what you discovered from probing the target site or data source. "
    "Your scrape logic and SKILL.md must be grounded in this evidence. "
    "When in doubt, probe deeper — **never** invent page structures or fields."
)
_REPAIR_HEADER: Final[str] = (
    "【Skill 修复 · 务必遵守】\n"
    "Skill `{}` either failed at runtime or produced no usable conclusion. "
    "**Preferred fix**: edit `main.py` via `update_uploaded_skill_file`, "
    "adjust according to research materials, then `run_skill_script` to re-verify. "
    "**Do NOT** create a brand-new Skill via `create_skill` unless the change is "
    "so large that patching is impractical — or the user explicitly asks for one.\n"
    "{}"
)
_RETRIEVAL_HEADER: Final[str] = (
    "【已检索材料】Context blocks are sorted by source priority: "
    "Knowledge Graph → Document Library → Web Search. "
    "Use bracketed numbers [n] to cite them in your answer. "
    "Avoid re-fetching material you already have."
)
_TURN_TOOLS_HEADER: Final[str] = (
    "These tool calls already finished during this turn's processing. "
    "Their full outputs appear in the tool-role messages below. "
    "**Do not re-invoke** unless the user changes their parameters or goal."
)

__all__ = [
    "append_retrieval_context",
    "append_skill_explore_context",
    "append_skill_repair_context",
    "build_retrieval_context_block",
    "build_skill_explore_context_block",
    "build_skill_repair_context_block",
    "build_turn_executed_tools_context",
    "compress_tool_result_for_loop",
    "has_skill_research_context",
    "inject_retrieval_context_message",
    "lookup_cached_tool_result",
    "normalize_tool_args_for_fingerprint",
    "record_executed_tool_call",
    "tool_call_args_preview",
    "tool_call_fingerprint",
    "trim_agent_loop_messages",
]


# ── Tool 结果压缩 ─────────────────────────────────────────────────────────────


def compress_tool_result_for_loop(
    raw: str,
    *,
    max_chars: int = 2800,
    context_preview_chars: int = 900,
) -> str:
    """将 tool JSON 压缩为要点：summary + 计数 + 短预览，避免撑爆 prompt。"""
    return _compress_tool_result(raw, max_chars=max_chars, context_preview_chars=context_preview_chars)


# ── 上下文拼接（检索 / 调研 / 修复 / 工具记录）─────────────────────────────────


def _concat_and_truncate(
    parts: list[str],
    *,
    max_chars: int,
    sep: str = "\n\n",
) -> tuple[str, list[str]]:
    """合并文本列表并截断；返回 (combined, new_parts)。超过预算时重置为截断后的单段。"""
    combined = sep.join(parts)
    if len(combined) <= max_chars:
        return combined, parts
    combined = truncate_to_budget(combined, max_chars)
    return combined, [combined]


def append_retrieval_context(loop_state: LoopState | None, context: str) -> None:
    """将检索片段写入 loop_state，供 system 层集中注入。"""
    if loop_state is None:
        return
    block = (context or "").strip()
    if not block:
        return
    parts: list[str] = list(loop_state.get("retrieval_context_parts") or [])
    parts.append(block)
    limits = get_prompt_limits()
    _, new_parts = _concat_and_truncate(parts, max_chars=limits["context_max_chars"])
    loop_state["retrieval_context_parts"] = new_parts


def append_skill_explore_context(loop_state: LoopState | None, block: str) -> None:
    """Skill 编写前调研结论写入 loop_state，避免旧 tool 消息被压缩后丢失。"""
    if loop_state is None:
        return
    text = (block or "").strip()
    if not text:
        return
    parts: list[str] = list(loop_state.get("skill_explore_parts") or [])
    parts.append(text)
    _, new_parts = _concat_and_truncate(parts, max_chars=_MAX_SKILL_EXPLORE_CHARS)
    loop_state["skill_explore_parts"] = new_parts


def build_skill_explore_context_block(loop_state: LoopState | None) -> str:
    parts = list((loop_state or {}).get("skill_explore_parts") or [])
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return f"{_SKILL_EXPLORE_HEADER}\n\n{body}"


def append_skill_repair_context(
    loop_state: LoopState | None,
    *,
    skill_name: str,
    reason: str,
) -> None:
    """已有 Skill 执行失败时写入修复指引。"""
    if loop_state is None:
        return
    name = (skill_name or "").strip()
    detail = (reason or "").strip()
    if not name or not detail:
        return
    attempts = dict(loop_state.get("skill_repair_attempts") or {})
    attempts[name] = attempts.get(name, 0) + 1
    loop_state["skill_repair_attempts"] = attempts
    loop_state["pending_skill_repair"] = name
    parts: list[str] = list(loop_state.get("skill_repair_parts") or [])
    parts.append(f"- `{name}`：{detail}")
    loop_state["skill_repair_parts"] = parts[-_MAX_SKILL_REPAIR_RECORDS:]


def build_skill_repair_context_block(loop_state: LoopState | None) -> str:
    pending = str((loop_state or {}).get("pending_skill_repair") or "").strip()
    parts = list((loop_state or {}).get("skill_repair_parts") or [])
    if not pending or not parts:
        return ""
    body = "\n".join(parts)
    return _REPAIR_HEADER.format(pending, body)


def has_skill_research_context(
    loop_state: LoopState | None, *, needs_site_research: bool
) -> bool:
    """网页/抓取类 Skill 在 create 前须已有调研上下文。"""
    if not needs_site_research:
        return True
    state = loop_state or {}
    return bool(
        state.get("skill_explore_parts")
        or state.get("retrieval_context_parts")
        or state.get("subagent_summaries")
    )


# ── 工具调用指纹（去重）────────────────────────────────────────────────────────


def normalize_tool_args_for_fingerprint(raw_args: str | dict | None) -> str:
    """将工具参数规范化为排序后的 JSON 字符串，用于指纹比较。"""
    if raw_args is None:
        return "{}"
    if isinstance(raw_args, dict):
        obj = raw_args
    else:
        text = str(raw_args).strip() or "{}"
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return text[:500]
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def tool_call_fingerprint(tool_name: str, raw_args: str | dict | None) -> str:
    """生成工具调用的唯一指纹（SHA256 前 16 字符）。"""
    payload = f"{(tool_name or '').strip()}\0{normalize_tool_args_for_fingerprint(raw_args)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def tool_call_args_preview(raw_args: str | dict | None, *, max_len: int = 120) -> str:
    preview = normalize_tool_args_for_fingerprint(raw_args)
    if len(preview) <= max_len:
        return preview
    return preview[:max_len-1] + "…"


def lookup_cached_tool_result(
    loop_state: LoopState | None,
    tool_name: str,
    raw_args: str | dict | None,
) -> str | None:
    """查询工具调用的缓存结果。"""
    fp = tool_call_fingerprint(tool_name, raw_args)
    cache = (loop_state or {}).get("executed_tool_cache") or {}
    hit = cache.get(fp)
    return str(hit) if hit is not None else None


def record_executed_tool_call(
    loop_state: LoopState,
    *,
    tool_name: str,
    raw_args: str | dict | None,
    result_text: str,
    summary: str,
    step_id: str,
) -> None:
    """记录已执行的工具调用及其结果摘要。"""
    fp = tool_call_fingerprint(tool_name, raw_args)
    records: list[dict[str, Any]] = list(loop_state.get("executed_tool_calls") or [])
    records.append({
        "fingerprint": fp,
        "tool_name": (tool_name or "").strip(),
        "args_preview": tool_call_args_preview(raw_args),
        "summary": (summary or "").strip()[:240],
        "step_id": (step_id or "").strip(),
    })
    loop_state["executed_tool_calls"] = records[-_MAX_TOOL_RECORDS:]
    cache: dict[str, str] = dict(loop_state.get("executed_tool_cache") or {})
    cache[fp] = result_text
    loop_state["executed_tool_cache"] = cache


_TOOL_ACTION_REPLAY_PREFIXES = (
    "使用联网搜索查询",
    "使用联网搜索搜索",
    "使用搜索引擎查询",
    "联网检索返回",
    "获取网页内容",
)


def _is_tool_action_replay_summary(summary: str) -> bool:
    """判断工具 call summary 是否仅为操作回顾（不含实质结果数据）。"""
    text = (summary or "").strip()
    if not text:
        return True
    for prefix in _TOOL_ACTION_REPLAY_PREFIXES:
        if text.startswith(prefix):
            return True
    return False


def build_turn_executed_tools_context(loop_state: LoopState | None) -> str:
    records = list((loop_state or {}).get("executed_tool_calls") or [])
    if not records:
        return ""
    lines: list[str] = []
    for idx, rec in enumerate(records, 1):
        name = str(rec.get("tool_name") or "tool").strip()
        args = str(rec.get("args_preview") or "").strip()
        summary = str(rec.get("summary") or "完成").strip()
        sid = str(rec.get("step_id") or "").strip()
        # 跳过纯工具操作回顾（如"联网检索返回X条"），不污染终稿 prompt
        if summary and _is_tool_action_replay_summary(summary):
            continue
        label = f"[{sid}] " if sid else ""
        arg_part = f"({args})" if args and args != "{}" else ""
        lines.append(f"{idx}. {label}{name}{arg_part} → {summary}")
    if not lines:
        return ""
    return (
        f"{_TURN_TOOLS_MARKER}{_TURN_TOOLS_HEADER}\n"
        + "\n".join(lines)
    )


# ── 检索材料块 ────────────────────────────────────────────────────────────────


def build_retrieval_context_block(loop_state: LoopState | None) -> str:
    from app.core.platform_assistant import assistant_conclusion_source_priority

    parts = list((loop_state or {}).get("retrieval_context_parts") or [])
    if not parts:
        return ""
    body = "\n\n".join(parts)
    source_priority = assistant_conclusion_source_priority()
    return f"{_RETRIEVAL_HEADER}\n{source_priority}\n\n{body}"


# ── 上下文注入（合并多块到 system 消息）────────────────────────────────────────


def inject_retrieval_context_message(
    messages: list[dict[str, Any]],
    loop_state: LoopState | None,
) -> list[dict[str, Any]]:
    """用最新检索/调研/修复/工具上下文替换或追加 system 消息。"""
    blocks: list[str] = []
    for builder in (
        build_skill_explore_context_block,
        build_skill_repair_context_block,
        build_turn_executed_tools_context,
        build_retrieval_context_block,
    ):
        block = builder(loop_state)
        if block:
            blocks.append(block)

    block = "\n\n".join(blocks).strip()
    if not block:
        return messages

    out = [dict(m) for m in messages]
    for idx, msg in enumerate(out):
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        if any(marker in content for marker in _TURN_MARKERS):
            head = content
            for marker in _TURN_MARKERS:
                if marker in head:
                    head = head.split(marker, 1)[0].rstrip()
            out[idx]["content"] = f"{head}\n\n{block}".strip() if head else block
            return out

    out.append({"role": "system", "content": block})
    return out


# ── 消息裁剪 ──────────────────────────────────────────────────────────────────


def trim_agent_loop_messages(
    messages: list[dict[str, Any]],
    *,
    max_total_chars: int | None = None,
    keep_full_tool_results: int = 1,
    reserve_for_tool_calls: int = 0,
) -> list[dict[str, Any]]:
    """裁剪 agent 循环 messages：旧 tool 只留 summary，总长度受 prompt 预算约束。

    Args:
        reserve_for_tool_calls: 为后续 tool_calls 预留的字符数，
            传递至 fit_messages_to_total_budget。
    """
    budget = max_total_chars or get_prompt_limits()["prompt_max_chars"]
    rows = [dict(m) for m in messages]

    tool_indices = [i for i, m in enumerate(rows) if m.get("role") == "tool"]
    for idx in tool_indices[:-keep_full_tool_results]:
        rows[idx]["content"] = compress_tool_result_for_loop(
            str(rows[idx].get("content") or ""),
            max_chars=420,
            context_preview_chars=0,
        )

    return fit_messages_to_total_budget(
        rows, budget, reserve_for_tool_calls=reserve_for_tool_calls,
    )
