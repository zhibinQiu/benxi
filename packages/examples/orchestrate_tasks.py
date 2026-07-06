# pip install agentkit-orchestrate
"""演示任务编排的基本用法：路由 → 任务 → 验收。"""

from agentkit_orchestrate import (
    VerifyHooks,
    VerifyRules,
    tasks_from_routes,
    verify_task_result,
)
from agentkit_orchestrate.types import OrchestratorTask
from agentkit_route.types import AgentRoute

# 定义路由
routes = [
    AgentRoute("research", "资料检索"),
]

# 路由 → 任务清单
tasks = tasks_from_routes(routes, title_fn=lambda a: f"专精: {a}")
task = tasks[0]
print(f"任务: id={task.id}, title={task.title}, agent={task.agent_id}")

# 构造验收规则与钩子
rules = VerifyRules(action_agent_ids=frozenset({"research"}))
hooks = VerifyHooks(
    is_substantive_deliverable=lambda t: len(t) > 20,
    reply_looks_like_denial=lambda t: "无法" in t,
)

# 模拟完整事件
complete = {
    "reply": "检索完成，共 12 条结果。关键发现：AI 政策在 2024 年有重大更新。",
    "citations": [{"url": "https://example.com/policy"}],
}
events = [{
    "type": "workflow",
    "data": {
        "phase": "tool_result",
        "status": "ok",
        "detail": "web-search: 搜索成功",
    },
}]

# 验收
ok, summary, hint = verify_task_result(task, events, complete, rules=rules, hooks=hooks)
print(f"验收: ok={ok}, summary={summary}")
