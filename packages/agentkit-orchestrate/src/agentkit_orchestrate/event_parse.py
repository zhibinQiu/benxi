"""从 workflow 事件流提取工具观测。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def successful_tool_summaries_in_events(
    events: list[dict[str, Any]],
    *,
    is_internal_line: Callable[[str], bool] | None = None,
) -> list[str]:
    """提取 tool_result 阶段的成功摘要（可过滤内部占位行）。"""
    internal = is_internal_line or (lambda _t: False)
    summaries: list[str] = []
    for event in events:
        if event.get("type") != "workflow":
            continue
        data = event.get("data") or {}
        if data.get("phase") != "tool_result":
            continue
        if data.get("status") == "failed":
            continue
        detail = str(data.get("detail") or "").strip()
        title = str(data.get("result_title") or data.get("title") or "").strip()
        text = detail or title
        if not text or internal(text):
            continue
        if title and internal(f"{title}：{detail}"):
            continue
        summaries.append(text)
    return summaries


def tool_failed_in_events(events: list[dict[str, Any]]) -> tuple[bool, str]:
    lines = tool_failure_lines_in_events(events)
    if lines:
        return True, lines[0][:160]
    return False, ""


def tool_failure_lines_in_events(events: list[dict[str, Any]]) -> list[str]:
    """提取 workflow 中全部失败工具摘要（供调度改正指引）。"""
    lines: list[str] = []
    for event in events:
        if event.get("type") != "workflow":
            continue
        data = event.get("data") or {}
        if data.get("phase") != "tool_result":
            continue
        if data.get("status") != "failed":
            continue
        tool = str(data.get("tool_name") or data.get("tool") or "").strip()
        detail = str(data.get("detail") or data.get("title") or "工具失败").strip()
        line = f"{tool}: {detail}" if tool else detail
        if line and line not in lines:
            lines.append(line[:240])
    return lines
