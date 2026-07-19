"""agentkit-subagent — 隔离上下文子 Agent 运行时。"""

from app.agentkit import __version__  # noqa: F401

from app.agentkit.subagent.config import SubagentConfig
from app.agentkit.subagent.context import (
    child_state_from_parent,
    merge_child_into_parent,
    normalize_queries,
)
from app.agentkit.subagent.loop import run_subagent_tool_loop
from app.agentkit.subagent.runtime import execute_subagent
from app.agentkit.subagent.types import SubagentKindConfig, SubagentRuntime
from app.agentkit.subagent.types import (
    LlmCompletionFn,
    SkillInvokeFn,
    ToolExecuteFn,
    ToolRecordFn,
)

__all__ = [
    "LlmCompletionFn",
    "SkillInvokeFn",
    "SubagentConfig",
    "SubagentKindConfig",
    "SubagentRuntime",
    "ToolExecuteFn",
    "ToolRecordFn",
    "child_state_from_parent",
    "execute_subagent",
    "merge_child_into_parent",
    "normalize_queries",
    "run_subagent_tool_loop",
]
