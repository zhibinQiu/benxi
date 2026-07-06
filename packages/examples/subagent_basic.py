# pip install agentkit-subagent
"""演示子 Agent 的基本配置与 query 归一化。"""

from agentkit_subagent import (
    SubagentConfig,
    SubagentRuntime,
    normalize_queries,
)

# 配置子 Agent 运行时
runtime = SubagentRuntime(
    kinds={},
    max_parallel_queries=4,
)

# 最小配置
config = SubagentConfig.minimal(runtime=runtime)
print(f"运行时 kinds: {len(config.runtime.kinds)}")
print(f"最大并行查询数: {config.runtime.max_parallel_queries}")

# 演示 query 归一化
queries = normalize_queries(
    "原始任务描述",
    [" 查询 1 ", "查询 2", " 查询 1 ", "查询 3"],
    max_queries=4,
)
print(f"归一化后的 queries: {queries}")

# 空 queries 回退到 task
fallback = normalize_queries("回退任务", None)
print(f"回退 queries: {fallback}")
