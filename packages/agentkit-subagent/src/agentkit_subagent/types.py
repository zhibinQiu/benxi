"""子 Agent 运行时 Protocol 与配置类型。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# ── 原子依赖类型别名 ──────────────────────────────────────────────

LlmCompletionFn = Callable[
    [list[dict[str, Any]], list[dict[str, Any]] | None],
    Awaitable[dict[str, Any] | None],
]
"""LLM completion：(messages, tool_specs) → choice dict | None"""

ToolExecuteFn = Callable[[str, Any], Awaitable[str]]
"""原子 tool 执行：(tool_name, arguments) → result_text"""

ToolRecordFn = Callable[
    [dict[str, Any], str, Any, str, str, str],
    None,
]
"""记录 tool 调用到 loop_state"""

SkillInvokeFn = Callable[[dict[str, Any], str, str, str, str], Awaitable[str]]
"""invoke_skill 步骤：(child_state, skill, action, param_key, query) → summary_text"""


class MessageNormalizer(Protocol):
    """将 LLM choice 中的 message 转为规范格式。"""

    def __call__(self, message: Any) -> dict[str, Any]: ...


class TextSanitizer(Protocol):
    """清理 LLM 输出中的标记或控制字符。"""

    def __call__(self, text: str) -> str: ...


class RetrievalAppender(Protocol):
    """将检索结果追加到 loop_state。"""

    def __call__(self, state: dict[str, Any], text: str) -> None: ...


class ToolSpecBuilder(Protocol):
    """根据允许工具名集合构建 tool 规范列表。"""

    def __call__(self, allowed_tools: set[str]) -> list[dict[str, Any]]: ...


# ── 配置类型 ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SubagentKindConfig:
    """单种 subagent 的行为配置。"""

    kind: str
    allowed_tools: frozenset[str]
    system_contract: str
    max_rounds: int = 8


@dataclass(frozen=True, slots=True)
class ExploreSkillStep:
    """并行 explore 单步：skill_name + action + params 中的 query 键名。"""

    skill_name: str
    action: str
    param_key: str = "query"


@dataclass(frozen=True, slots=True)
class SubagentRuntime:
    """子 Agent 全局运行时配置。"""

    kinds: dict[str, SubagentKindConfig] = field(default_factory=dict)
    explore_steps: tuple[ExploreSkillStep, ...] = ()
    max_parallel_queries: int = 4
    parallel_explore_min_queries: int = 2
