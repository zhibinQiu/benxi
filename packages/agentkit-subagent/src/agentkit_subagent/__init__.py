"""agentkit-subagent — 隔离上下文子 Agent 运行时。"""

__version__ = "4.6.0"

from agentkit_subagent.config import SubagentConfig
from agentkit_subagent.context import (
    child_state_from_parent,
    merge_child_into_parent,
    normalize_queries,
)
from agentkit_subagent.explore import ExploreSkillStep, parallel_explore_queries
from agentkit_subagent.loop import run_subagent_tool_loop
from agentkit_subagent.runtime import execute_subagent
from agentkit_subagent.types import SubagentKindConfig, SubagentRuntime
from agentkit_subagent.types import (
    LlmCompletionFn,
    SkillInvokeFn,
    ToolExecuteFn,
    ToolRecordFn,
)

__all__ = [
    "ExploreSkillStep",
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
    "parallel_explore_queries",
    "run_subagent_tool_loop",
]
