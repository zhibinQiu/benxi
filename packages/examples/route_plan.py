# pip install agentkit-route
"""演示多智能体路由的基本用法：路由构建、模式推断、上限截断。"""

from agentkit_route import (
    AgentRoute,
    RouteLimits,
    build_route_plan,
    infer_route_mode,
)

# 定义候选路由
routes = [
    AgentRoute("research", "资料检索"),
    AgentRoute("report", "撰写报告"),
]

# 推断路由模式
mode = infer_route_mode(
    "先检索资料然后写报告",
    len(routes),
    limits=RouteLimits(max_sequential_handoffs=3),
)
print(f"路由模式: {mode}")

# 构建路由计划
plan = build_route_plan(mode, routes, source="skill")
print(f"执行计划: mode={plan.mode}, routes={[r.agent_id for r in plan.routes]}")

# 演示上限截断
capped = plan.routes[:1]
print(f"截断后: {[r.agent_id for r in capped]}")
