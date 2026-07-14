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
    """提取 workflow 中失败工具摘要（供调度改正指引）。

    同一工具名有多个 tool_result 时只取最后一个状态——如果最终成功则不计为失败。
    优先使用 resultDetail（实际错误信息）补充 detail 的不足。
    """
    # 先遍历所有 tool_result，记录每个工具名的最后状态
    last_status: dict[str, str] = {}
    last_detail: dict[str, str] = {}
    last_result_detail: dict[str, str] = {}
    for event in events:
        if event.get("type") != "workflow":
            continue
        data = event.get("data") or {}
        if data.get("phase") != "tool_result":
            continue
        tool = str(data.get("tool_name") or data.get("tool") or "").strip()
        if not tool:
            continue
        last_status[tool] = str(data.get("status") or "done")
        last_detail[tool] = str(data.get("detail") or data.get("title") or "工具失败").strip()
        rd = str(data.get("resultDetail") or "").strip()
        if rd:
            last_result_detail[tool] = rd

    # 只报告最终状态为失败的工具
    lines: list[str] = []
    for tool, status in last_status.items():
        if status != "failed":
            continue
        detail = last_detail.get(tool, "工具失败")
        # 如果 detail 是泛化的"失败"但有具体 resultDetail，用后者
        result_detail = last_result_detail.get(tool, "")
        if result_detail and detail in ("失败", "工具失败"):
            detail = result_detail[:240]
        line = f"{tool}: {detail}" if tool else detail
        if line and line not in lines:
            lines.append(line[:240])
    return lines
