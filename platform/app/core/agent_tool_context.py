"""Agent 工具循环上下文管理 — 压缩 tool 输出、集中注入检索材料。"""

from __future__ import annotations

import json
from typing import Any

from app.core.prompt_budget import fit_messages_to_total_budget, get_prompt_limits, truncate_to_budget
from app.core.text_utils import truncate_text

_LARGE_DATA_KEYS = frozenset(
    {
        "screenshot_base64",
        "screenshot_url",
        "storage_key",
        "html",
        "snapshot",
        "raw_html",
        "page_content",
        "markdown",
    }
)
_CONTEXT_KEYS = frozenset({"context", "context_text"})
_LIST_PREVIEW_KEYS = frozenset({"hits", "items", "refs", "citations", "rows"})


def compress_tool_result_for_loop(
    raw: str,
    *,
    max_chars: int = 2800,
    context_preview_chars: int = 900,
) -> str:
    """将 tool JSON 压缩为要点：summary + 计数 + 短预览，避免撑爆 prompt。"""
    text = (raw or "").strip()
    if not text:
        return text
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return truncate_text(text, max_chars)

    if not isinstance(body, dict):
        return truncate_text(text, max_chars)

    summary = str(body.get("summary") or "").strip()
    data = body.get("data")
    compact_data = _compact_tool_data(
        data,
        context_preview_chars=context_preview_chars,
    )
    compact: dict[str, Any] = {
        "ok": body.get("ok"),
        "summary": summary,
    }
    if compact_data is not None:
        compact["data"] = compact_data

    out = json.dumps(compact, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    if isinstance(compact_data, dict) and compact_data.get("context_preview"):
        compact_data["context_preview"] = truncate_text(
            str(compact_data["context_preview"]),
            max(200, max_chars // 3),
        )
        compact["data"] = compact_data
        out = json.dumps(compact, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    if summary:
        return json.dumps(
            {"ok": body.get("ok"), "summary": truncate_text(summary, max_chars - 80)},
            ensure_ascii=False,
        )
    return truncate_text(out, max_chars)


def _compact_tool_data(
    data: Any,
    *,
    context_preview_chars: int,
) -> Any:
    if data is None:
        return None
    if not isinstance(data, dict):
        s = str(data)
        return s if len(s) <= 800 else truncate_text(s, 800)

    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in _LARGE_DATA_KEYS:
            continue
        if key in _CONTEXT_KEYS:
            text = str(value or "").strip()
            if text:
                preview = text.replace("\n", " ")
                out["context_preview"] = truncate_text(preview, context_preview_chars)
                out["context_chars"] = len(text)
            continue
        if key in _LIST_PREVIEW_KEYS and isinstance(value, list):
            out[f"{key}_count"] = len(value)
            if value and key == "hits":
                snippets: list[str] = []
                for item in value[:2]:
                    if not isinstance(item, dict):
                        continue
                    snip = (
                        item.get("snippet")
                        or item.get("highlight")
                        or item.get("content")
                        or ""
                    )
                    snip = str(snip).strip().replace("\n", " ")
                    if snip:
                        snippets.append(truncate_text(snip, 120))
                if snippets:
                    out["snippet_preview"] = " | ".join(snippets)
            continue
        if isinstance(value, str) and len(value) > 1200:
            out[key] = truncate_text(value, 1200)
        elif isinstance(value, (dict, list)):
            serialized = json.dumps(value, ensure_ascii=False)
            if len(serialized) > 1200:
                out[key] = truncate_text(serialized, 1200)
            else:
                out[key] = value
        else:
            out[key] = value
    return out or None


def append_retrieval_context(loop_state: dict[str, Any] | None, context: str) -> None:
    """将检索片段写入 loop_state，供 system 层集中注入（tool 消息不再重复全文）。"""
    if loop_state is None:
        return
    block = (context or "").strip()
    if not block:
        return
    parts: list[str] = list(loop_state.get("retrieval_context_parts") or [])
    parts.append(block)
    limits = get_prompt_limits()
    combined = "\n\n".join(parts)
    if len(combined) > limits["context_max_chars"]:
        combined = truncate_to_budget(combined, limits["context_max_chars"])
        parts = [combined]
    loop_state["retrieval_context_parts"] = parts


def append_skill_explore_context(loop_state: dict[str, Any] | None, block: str) -> None:
    """Skill 编写前调研结论写入 loop_state，避免旧 tool 消息被压缩后丢失关键上下文。"""
    if loop_state is None:
        return
    text = (block or "").strip()
    if not text:
        return
    parts: list[str] = list(loop_state.get("skill_explore_parts") or [])
    parts.append(text)
    combined = "\n\n".join(parts)
    if len(combined) > 2400:
        combined = truncate_to_budget(combined, 2400)
        parts = [combined]
    loop_state["skill_explore_parts"] = parts


def build_skill_explore_context_block(loop_state: dict[str, Any] | None) -> str:
    parts = list((loop_state or {}).get("skill_explore_parts") or [])
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return (
        "【Skill 编写调研材料 · 创建前必读】\n"
        "以下来自你对目标站点/数据源的探查；"
        "编写 scrape 逻辑与 SKILL.md 时必须以此为准，"
        "信息不足时继续探查，**勿**猜测页面结构或字段。\n\n"
        f"{body}"
    )


def append_skill_repair_context(
    loop_state: dict[str, Any] | None,
    *,
    skill_name: str,
    reason: str,
) -> None:
    """已有 Skill 执行失败时写入修复指引，供后续 tool loop 轮次注入。"""
    if loop_state is None:
        return
    name = (skill_name or "").strip()
    detail = (reason or "").strip()
    if not name or not detail:
        return
    attempts = dict(loop_state.get("skill_repair_attempts") or {})
    attempts[name] = int(attempts.get(name) or 0) + 1
    loop_state["skill_repair_attempts"] = attempts
    loop_state["pending_skill_repair"] = name
    parts: list[str] = list(loop_state.get("skill_repair_parts") or [])
    parts.append(f"- `{name}`：{detail}")
    loop_state["skill_repair_parts"] = parts[-4:]


def build_skill_repair_context_block(loop_state: dict[str, Any] | None) -> str:
    pending = str((loop_state or {}).get("pending_skill_repair") or "").strip()
    parts = list((loop_state or {}).get("skill_repair_parts") or [])
    if not pending or not parts:
        return ""
    body = "\n".join(parts)
    return (
        "【Skill 修复 · 务必遵守】\n"
        f"发展技能 `{pending}` 执行失败或未产出有效结论。"
        "请**优先**用 `update_uploaded_skill_file` 修复该技能的 `main.py` / `workflow.json` / `SKILL.md`，"
        "依据上方调研材料或最新报错调整；修复后再次 `run_skill_script` 验证是否满足用户需求。"
        "**禁止**为此重复 `create_uploaded_skill` 造新技能，除非改动过大或用户明确要求新建。\n"
        f"{body}"
    )


def has_skill_research_context(
    loop_state: dict[str, Any] | None, *, needs_site_research: bool
) -> bool:
    """网页/抓取类 Skill 在 create 前须已有调研上下文。"""
    if not needs_site_research:
        return True
    state = loop_state or {}
    if state.get("skill_explore_parts"):
        return True
    if state.get("retrieval_context_parts"):
        return True
    return False


def build_retrieval_context_block(loop_state: dict[str, Any] | None) -> str:
    from app.core.platform_assistant import assistant_conclusion_source_priority

    parts = list((loop_state or {}).get("retrieval_context_parts") or [])
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return (
        "【已检索材料】上下文顺序与引用编号已按优先级排列：本体图谱 → 文档库 → 联网检索。\n"
        f"{assistant_conclusion_source_priority()}\n\n"
        "以下编号 [n] 可直接用于回答引用；勿重复调用相同检索。\n\n"
        f"{body}"
    )


def inject_retrieval_context_message(
    messages: list[dict[str, Any]],
    loop_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """用最新检索块替换/追加 system 消息，避免 tool 历史重复携带全文。"""
    blocks: list[str] = []
    skill_block = build_skill_explore_context_block(loop_state)
    if skill_block:
        blocks.append(skill_block)
    repair_block = build_skill_repair_context_block(loop_state)
    if repair_block:
        blocks.append(repair_block)
    retrieval_block = build_retrieval_context_block(loop_state)
    if retrieval_block:
        blocks.append(retrieval_block)
    block = "\n\n".join(blocks).strip()
    if not block:
        return messages

    marker = "【已检索材料】"
    skill_marker = "【Skill 编写调研材料"
    repair_marker = "【Skill 修复"
    out = [dict(m) for m in messages]
    for idx, msg in enumerate(out):
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        if marker in content or skill_marker in content or repair_marker in content:
            head = content
            if marker in head:
                head = head.split(marker, 1)[0].rstrip()
            if skill_marker in head:
                head = head.split(skill_marker, 1)[0].rstrip()
            if repair_marker in head:
                head = head.split(repair_marker, 1)[0].rstrip()
            out[idx]["content"] = f"{head}\n\n{block}".strip() if head else block
            return out

    out.append({"role": "system", "content": block})
    return out


def trim_agent_loop_messages(
    messages: list[dict[str, Any]],
    *,
    max_total_chars: int | None = None,
    keep_full_tool_results: int = 1,
) -> list[dict[str, Any]]:
    """裁剪 agent 循环 messages：旧 tool 只留 summary，总长度受 prompt 预算约束。"""
    budget = max_total_chars or get_prompt_limits()["prompt_max_chars"]
    rows = [dict(m) for m in messages]

    tool_indices = [i for i, m in enumerate(rows) if m.get("role") == "tool"]
    for idx in tool_indices[:-keep_full_tool_results]:
        rows[idx]["content"] = compress_tool_result_for_loop(
            str(rows[idx].get("content") or ""),
            max_chars=420,
            context_preview_chars=0,
        )

    return fit_messages_to_total_budget(rows, budget)
