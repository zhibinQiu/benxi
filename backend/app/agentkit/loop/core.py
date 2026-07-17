"""Loop Engineering — 六相循环终稿阶段的动态上下文组装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from app.agentkit.loop.state import LoopState

DEFAULT_LOOP_SYSTEM_CONTRACT = (
    "Agent 循环终稿阶段。依据下方「目标、智能体计划、观测证据」生成面向用户的答复。"
    "只引用证据中的事实；禁止复述工具执行状态；禁止让用户自行执行命令。"
)


@dataclass(frozen=True, slots=True)
class LoopEvidence:
    """终稿阶段注入 LLM 的结构化证据（均已截断以节约 token）。"""

    plan_instruction: str = ""
    tool_context: str = ""
    deliverable_evidence: str = ""
    extra_evidence: str = ""
    history_excerpt: str = ""


class LoopEvidenceProvider(Protocol):
    """从 loop_state 提取终稿证据；由宿主实现。"""

    def extract(self, loop_state: LoopState | None) -> LoopEvidence: ...


@dataclass(frozen=True, slots=True)
class LoopExitRequest:
    """循环退出阶段的 Prompt 构建请求。"""

    user_message: str
    loop_state: LoopState | None = None
    memory_context: str = ""
    system_contract: str = DEFAULT_LOOP_SYSTEM_CONTRACT
    user_message_limit: int = 1200


def build_agent_instruction_from_plan(
    plan: Any,
    *,
    reasoning_limit: int = 800,
    format_plan: Callable[[Any], str] | None = None,
) -> str:
    """从宿主规划器对象提取任务指令。"""
    if plan is None:
        return ""
    parts: list[str] = []
    reasoning = str(getattr(plan, "reasoning", "") or "").strip()
    if reasoning:
        parts.append(f"【规划说明】{reasoning[:reasoning_limit]}")
    if format_plan is not None:
        plan_instr = (format_plan(plan) or "").strip()
        if plan_instr:
            parts.append(plan_instr)
    return "\n".join(parts).strip()


def build_turn_tools_context(
    loop_state: LoopState | None,
    *,
    max_lines: int = 12,
    line_limit: int = 200,
) -> str:
    """从 loop_state 提取本轮已执行工具的短摘要。"""
    lines = (loop_state or {}).get("tool_outcome_lines") or []
    if not lines:
        return ""
    clipped = [str(line)[:line_limit] for line in list(lines)[-max_lines:]]
    return "【本轮工具观测】\n" + "\n".join(
        f"- {line}" for line in clipped if line.strip()
    )


def _build_dynamic_blocks(ev: LoopEvidence, user_msg: str, msg_limit: int) -> list[str]:
    """收集非空证据块。"""
    blocks: list[str] = [f"【目标】{user_msg[:msg_limit]}"]
    fields = [
        ("plan_instruction", ev.plan_instruction),
        ("tool_context", ev.tool_context),
        ("deliverable_evidence", ev.deliverable_evidence),
        ("extra_evidence", ev.extra_evidence),
        ("history_excerpt", ev.history_excerpt),
    ]
    for field_name, value in fields:
        stripped = value.strip() if value else ""
        if stripped:
            prefix = "【近期对话】" if field_name == "history_excerpt" else ""
            blocks.append(f"{prefix}\n{stripped}" if prefix else stripped)
    return blocks


def build_loop_exit_prompt_messages(
    request: LoopExitRequest,
    evidence: LoopEvidence | None = None,
    *,
    provider: LoopEvidenceProvider | None = None,
) -> list[dict[str, str]]:
    """循环退出阶段的动态 Prompt：system=契约，user=目标+计划+观测。

    ``evidence`` 与 ``provider`` 二选一；均未提供时使用空证据。
    """
    if evidence is None and provider is not None:
        evidence = provider.extract(request.loop_state)
    ev = evidence or LoopEvidence()

    blocks = _build_dynamic_blocks(ev, request.user_message, request.user_message_limit)
    memory = (request.memory_context or "").strip()
    user_blob = (f"{memory}\n\n" if memory else "") + "\n\n".join(blocks)
    return [
        {"role": "system", "content": request.system_contract},
        {"role": "user", "content": user_blob},
    ]


def dict_evidence_provider(
    *,
    format_plan: Callable[[Any], str] | None = None,
    deliverable_fn: Callable[[LoopState | None], str] | None = None,
) -> LoopEvidenceProvider:
    """基于通用 loop_state 键的默认 Provider 工厂。"""

    class _Provider:
        def extract(self, loop_state: LoopState | None) -> LoopEvidence:
            state = loop_state or {}
            plan = state.get("_execution_plan")
            plan_instr = build_agent_instruction_from_plan(plan, format_plan=format_plan)
            tool_ctx = build_turn_tools_context(state)
            deliverable = (deliverable_fn(state) if deliverable_fn else "").strip()
            return LoopEvidence(
                plan_instruction=plan_instr,
                tool_context=tool_ctx,
                deliverable_evidence=deliverable,
            )

    return _Provider()
