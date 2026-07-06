# pip install agentkit-aip
"""演示 AIP 会话消息总线的基本用法：handoff 构建、发布、读取。"""

from agentkit_aip import (
    AipSessionBus,
    HandoffBuilder,
    build_specialist_handoff_result,
    handoff_text_from_message,
)

bus = AipSessionBus()

# 专精智能体完成工作后构建 handoff
result = build_specialist_handoff_result(
    ok=True,
    text="检索完成，共找到 12 条相关结果",
    agent_id="research",
    session_id="sess-1",
    task_id="task-1",
    loop_state={"tool_outcome_lines": ["web-search: ok"]},
)
# 发布到会话总线
bus.publish("sess-1", result.message)

# 读取会话内 handoff
handoffs = bus.handoffs("sess-1")
for msg in handoffs:
    print("handoff 内容:", handoff_text_from_message(msg))

# 基于已有 handoff 构建下一条 task_request
user_msg = bus.format_task_request_for_llm(
    session_id="sess-1",
    task_id="task-2",
    target_agent_id="report",
    user_message="基于检索结果写摘要",
)
print("\n发送给 report 专精的消息:\n", user_msg)
