"""agentkit-loop — Loop Engineering 核心。

六相循环的 **终稿阶段** 实现：短 system 契约 + 动态 user 块（目标 / 计划 / 观测）。
宿主通过 ``LoopEvidenceProvider`` 注入业务字段，避免本库依赖具体 planner / tool 层。
"""

from app.agentkit import __version__  # noqa: F401

from app.agentkit.loop.core import (
    DEFAULT_LOOP_SYSTEM_CONTRACT,
    LoopEvidence,
    LoopEvidenceProvider,
    LoopExitRequest,
    build_agent_instruction_from_plan,
    build_loop_exit_prompt_messages,
    build_turn_tools_context,
    dict_evidence_provider,
)
from app.agentkit.loop.plan import AgentExecutionPlan, AgentToolPlan

__all__ = [
    "AgentExecutionPlan",
    "AgentToolPlan",
    "DEFAULT_LOOP_SYSTEM_CONTRACT",
    "LoopEvidence",
    "LoopEvidenceProvider",
    "LoopExitRequest",
    "build_agent_instruction_from_plan",
    "build_loop_exit_prompt_messages",
    "build_turn_tools_context",
    "dict_evidence_provider",
]
