"""app.agent.subagent — 隔离上下文子 Agent 运行时。"""

from app.agent import __version__  # noqa: F401

from app.agent.subagent.config import SubagentConfig
from app.agent.subagent.context import (
    child_state_from_parent,
    merge_child_into_parent,
    normalize_queries,
)
from app.agent.subagent.loop import run_subagent_tool_loop
from app.agent.subagent.runtime import execute_subagent
from app.agent.subagent.types import SubagentKindConfig, SubagentRuntime
from app.agent.subagent.types import (
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
