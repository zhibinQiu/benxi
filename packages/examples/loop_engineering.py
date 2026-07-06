# pip install agentkit-loop
"""演示 Loop Engineering 动态 Prompt 组装。"""

from agentkit_loop import (
    LoopExitRequest,
    build_loop_exit_prompt_messages,
    dict_evidence_provider,
)

# 模拟一个简单的 plan 对象
class SimplePlan:
    reasoning = "先检索资料，再汇总结果"

# 构造 loop_state
loop_state = {
    "_execution_plan": SimplePlan(),
    "tool_outcome_lines": [
        "web-search: 搜索到 12 条结果",
        "web-search: 搜索到 5 条结果",
    ],
}

# 构造证据提供者
provider = dict_evidence_provider(
    format_plan=lambda p: "【步骤】\n1. 检索\n2. 汇总",
    deliverable_fn=lambda s: s.get("report_excerpt", ""),
)

# 构建 LLM 消息
messages = build_loop_exit_prompt_messages(
    LoopExitRequest(
        user_message="帮我调研 AI 政策最新进展",
        loop_state=loop_state,
        system_contract="你是 AI 助手，基于观测证据回答问题。",
    ),
    provider=provider,
)

print("=== System ===")
print(messages[0]["content"])
print("\n=== User ===")
print(messages[1]["content"])
