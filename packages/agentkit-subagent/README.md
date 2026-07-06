# agentkit-subagent

隔离上下文 **Subagent** 运行时：并行 explore 与 LLM tool 循环，全部通过 Protocol 注入。

## 安装

```bash
pip install agentkit-subagent

# 本地开发
pip install -e packages/agentkit-subagent
```

## 快速开始

```python
from agentkit_subagent import SubagentConfig, SubagentRuntime, normalize_queries

runtime = SubagentRuntime(kinds={}, max_parallel_queries=4)
config = SubagentConfig.minimal(runtime=runtime)

# 查询归一化
queries = normalize_queries("调研 AI 政策", queries=["查询 1", "查询 2", "查询 1"])
print(queries)  # ["查询 1", "查询 2"]
```

## API 概览

| 函数/类 | 说明 |
|---------|------|
| `SubagentConfig` | 宿主依赖注入配置（替代 13 个松散参数） |
| `SubagentRuntime` | 子 Agent 全局运行时配置 |
| `execute_subagent()` | 统一入口：并行 explore / 隔离 tool 循环 |
| `normalize_queries()` | 去重并截断 query 列表 |
| `child_state_from_parent()` | 从父 loop_state 派生隔离子 state |
| `merge_child_into_parent()` | 将子 Agent 摘要合并回父 loop_state |
| `parallel_explore_queries()` | 多 query 并行 explore |
| `run_subagent_tool_loop()` | 隔离 LLM + tool 循环 |

## 宿主注入接口

`SubagentConfig` 通过以下 Protocol 注入宿主能力：

- `LlmCompletionFn` — LLM 补全调用
- `ToolExecuteFn` — 工具执行
- `ToolRecordFn` — 工具调用记录
- `SkillInvokeFn` — Skill 调用
- `RetrievalAppender` — 检索结果追加

## 示例

见 [examples/subagent_basic.py](../examples/subagent_basic.py)
