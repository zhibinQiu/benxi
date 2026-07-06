# agentkit-loop

**Loop Engineering** 核心 — 观测驱动的动态 Prompt 组装。

## 与 Prompt Engineering 的区别

| Prompt Engineering | Loop Engineering（本库） |
|-------------------|-------------------------|
| 堆叠长 system prompt | system 仅短 **循环契约** |
| 静态任务说明 | user 块 = 目标 + **规划器产出** + **工具观测** |
| 难以调试 | 每轮 tool 结果写入 loop_state，可追溯 |

## 安装

```python
pip install agentkit-loop
```

## 示例

```python
from agentkit_loop import LoopExitRequest, build_loop_exit_prompt_messages, dict_evidence_provider

loop_state = {
    "_execution_plan": type("Plan", (), {"reasoning": "先检索再汇总"})(),
    "tool_outcome_lines": ["web-search: 12 hits"],
}

provider = dict_evidence_provider(
    format_plan=lambda p: "【步骤】1. 检索 2. 汇总",
    deliverable_fn=lambda s: s.get("report_excerpt", ""),
)

messages = build_loop_exit_prompt_messages(
    LoopExitRequest(user_message="帮我调研 AI 政策", loop_state=loop_state),
    provider=provider,
)
# messages[0]["role"] == "system"  → 短契约
# messages[1]["role"] == "user"     → 动态证据块
```

## 六相循环映射

1. 输入捕获 → 宿主 `user_message` / planner
2. 上下文组装 → **本库** `build_loop_exit_prompt_messages`
3. 模型推理 → 宿主 LLM 客户端
4. 动作执行 → 宿主 tool 层
5. 观测校验 → 宿主 satisfaction 函数
6. 记忆更新 → 宿主写入 `loop_state`

## 更多示例

见 [examples/loop_engineering.py](../examples/loop_engineering.py)
