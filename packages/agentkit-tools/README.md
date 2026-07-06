# agentkit-tools

Agent 工具定义、Schema 生成、参数校验、结果压缩 — 每个 Agent 系统每天都会用到的实用层。

## 安装

```bash
pip install agentkit-tools

# 本地开发
pip install -e packages/agentkit-tools
```

## 模块概览

| 模块 | 职责 |
|------|------|
| `ToolRegistry` | 声明式工具注册：名称、描述、参数模型  → 函数调用 spec |
| `schema` | Pydantic Model → 紧凑 JSON Schema → OpenAI function calling 格式 |
| `validate` | 运行时参数校验，返回 `(cleaned_args, error_msg)` |
| `compress` | Tool JSON 结果压缩，控制 prompt 预算 |

## 快速开始

```python
from pydantic import BaseModel, Field
from agentkit_tools import ToolRegistry, validate_tool_arguments

# 1. 定义参数模型
class WebSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    max_items: int = Field(default=8, ge=1, le=20)

# 2. 注册工具
registry = ToolRegistry()
registry.register(
    "web_search",
    "联网检索公开信息",
    WebSearchArgs,
)

# 3. 生成 LLM 可用 spec
specs = registry.build_specs()
# → [{"type": "function", "function": {"name": "web_search", ...}}]

# 4. 验证 LLM 传入的参数
cleaned, error = validate_tool_arguments(
    registry, "web_search", {"query": "天气", "max_items": 5}
)
assert error is None
# cleaned = {"query": "天气", "max_items": 5}

# 5. 压缩工具结果
from agentkit_tools import compress_tool_result

compressed = compress_tool_result(
    '{"ok": true, "summary": "找到 3 条结果", "data": {...}}'
)
```

## 与现有 agentkit 包的关系

- **agentkit-route** — 智能体路由（哪个 agent 处理什么）
- **agentkit-subagent** — 隔离子 Agent 运行时
- **agentkit-loop** — 循环退出阶段动态 Prompt
- **agentkit-tools** — **填补缺失的底层工具层**：定义、校验、压缩
