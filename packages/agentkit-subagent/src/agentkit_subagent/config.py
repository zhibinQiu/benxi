"""子 Agent 调用配置 — 替代 13 参数函数的 Builder 模式。"""

from __future__ import annotations

from dataclasses import dataclass

from agentkit_subagent.types import (
    LlmCompletionFn,
    RetrievalAppender,
    SkillInvokeFn,
    SubagentRuntime,
    ToolExecuteFn,
    ToolRecordFn,
    ToolSpecBuilder,
)


@dataclass
class SubagentConfig:
    """子 Agent 执行配置：宿主注入依赖接口。
    
    替代 ``execute_subagent`` 的 13 个松散参数，通过 ``@dataclass`` 提供默认值，
    宿主仅需覆盖需要注入的字段。
    """

    # ── 必须注入 ────────────────────────────────────────────────
    runtime: SubagentRuntime
    llm_complete: LlmCompletionFn | None = None
    execute_tool: ToolExecuteFn | None = None
    record_tool: ToolRecordFn | None = None
    build_tool_specs: ToolSpecBuilder | None = None
    invoke_skill: SkillInvokeFn | None = None

    # ── 可选注入 ────────────────────────────────────────────────
    append_retrieval: RetrievalAppender | None = None
    normalize_message: Any = None
    strip_markup: Any = None

    @classmethod
    def minimal(
        cls,
        *,
        runtime: Any,
        llm_complete: LlmCompletionFn | None = None,
    ) -> SubagentConfig:
        """最小配置：仅 LLM + runtime，跳过 explore 和 tool loop。"""
        return cls(runtime=runtime, llm_complete=llm_complete)

    @classmethod
    def full(
        cls,
        *,
        runtime: Any,
        llm_complete: LlmCompletionFn,
        execute_tool: ToolExecuteFn,
        record_tool: ToolRecordFn,
        build_tool_specs: ToolSpecBuilder,
        invoke_skill: SkillInvokeFn,
        append_retrieval: RetrievalAppender | None = None,
    ) -> SubagentConfig:
        """完整配置：LLM + tool loop + explore。"""
        return cls(
            runtime=runtime,
            llm_complete=llm_complete,
            execute_tool=execute_tool,
            record_tool=record_tool,
            build_tool_specs=build_tool_specs,
            invoke_skill=invoke_skill,
            append_retrieval=append_retrieval,
        )
