"""Agent 流式通信协议 — 阶段约定（便于对接外部平台）。

标准循环::

    thinking → planning → executing →（再 thinking → planning → executing）…

并行执行时 ``stage=executing`` 且 ``mode`` 为 ``parallel`` / ``dag``，
``tasks`` 中多条 ``status=running`` 表示同一波次同时进行。

对外字段（workflow.data）::

    stage: thinking | planning | executing
    phase: 平台细粒度事件名（兼容存量前端）
    mode: sequential | parallel | dag（规划/执行时可选）
    tasks: [{id, title, status, agent_id, summary}]
    title / detail / tool / step_id: 人类可读摘要与追踪

OpenAI 兼容层将 stage 映射为 reasoning_content 行前缀
``[thinking]`` / ``[planning]`` / ``[executing]`` / ``[executing:parallel]``。
"""

from __future__ import annotations

from typing import Any

STAGE_THINKING = "thinking"
STAGE_PLANNING = "planning"
STAGE_EXECUTING = "executing"

STAGES = frozenset({STAGE_THINKING, STAGE_PLANNING, STAGE_EXECUTING})

# 细粒度 phase → 标准 stage
PHASE_TO_STAGE: dict[str, str] = {
    "workflow_started": STAGE_THINKING,
    "agent_thinking": STAGE_THINKING,
    "llm_thinking": STAGE_THINKING,
    "thinking_delta": STAGE_THINKING,
    "agent_thought": STAGE_THINKING,
    "plan_tasks": STAGE_PLANNING,
    "agent_plan": STAGE_PLANNING,
    "llm_decision": STAGE_PLANNING,
    "task_started": STAGE_EXECUTING,
    "task_retry": STAGE_EXECUTING,
    "tool_call": STAGE_EXECUTING,
    "url_parse_progress": STAGE_EXECUTING,
    "orchestrator_progress": STAGE_EXECUTING,
    "task_done": STAGE_EXECUTING,
    "task_failed": STAGE_EXECUTING,
    "tool_result": STAGE_EXECUTING,
}


def resolve_stage(phase: str, *, explicit: str | None = None) -> str:
    """解析标准 stage；explicit 优先。"""
    if explicit and explicit in STAGES:
        return explicit
    return PHASE_TO_STAGE.get(str(phase or "").strip(), "")


def enrich_workflow_data(data: dict[str, Any]) -> dict[str, Any]:
    """为 workflow 事件补齐 ``stage``（原地修改并返回）。"""
    if not isinstance(data, dict):
        return data
    phase = str(data.get("phase") or "").strip()
    explicit = str(data.get("stage") or "").strip() or None
    stage = resolve_stage(phase, explicit=explicit)
    if stage:
        data["stage"] = stage
    return data


def running_task_titles(tasks: list[Any] | None) -> list[str]:
    """提取并行执行中的任务标题。"""
    out: list[str] = []
    for raw in tasks or []:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "").strip()
        if status != "running":
            continue
        title = str(raw.get("title") or "").strip()
        if title:
            out.append(title)
    return out


def format_reasoning_line(data: dict[str, Any]) -> str:
    """OpenAI reasoning_content 单行（标准前缀，外部平台可解析）。"""
    phase = str(data.get("phase") or "").strip()
    stage = resolve_stage(phase, explicit=str(data.get("stage") or "").strip() or None)
    title = str(data.get("title") or "").strip()
    detail = str(data.get("detail") or "").strip()
    tool = str(data.get("tool") or "").strip()

    if phase == "thinking_delta":
        # 兼容旧流；新路径不再逐字推送
        return str(data.get("delta") or "")

    if stage == STAGE_THINKING:
        # 避免「思考完成」刷屏
        if phase == "agent_thought" and str(data.get("status") or "") == "done":
            return ""
        return "[thinking]\n"

    if stage == STAGE_PLANNING:
        body = detail or title
        return f"[planning] {body}\n" if body else "[planning]\n"

    if stage == STAGE_EXECUTING:
        running = running_task_titles(data.get("tasks") if isinstance(data.get("tasks"), list) else None)
        # 仅「多段同时 running」标 parallel；mode=dag/parallel 但单任务仍用普通 executing
        if len(running) > 1:
            return f"[executing:parallel] {' || '.join(running)}\n"
        if phase == "tool_call":
            head = tool or title or "tool"
            body = detail or title
            if body and body != head:
                return f"[executing] {head}: {body}\n"
            return f"[executing] {head}\n"
        if phase == "tool_result":
            status = str(data.get("status") or "done").strip() or "done"
            body = detail or title
            if not body:
                return ""
            return f"[executing] [{status}] {body}\n"
        body = title or detail
        return f"[executing] {body}\n" if body else "[executing]\n"

    return ""
