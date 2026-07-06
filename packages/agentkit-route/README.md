# agentkit-route

多智能体 **路由类型** 与 **纯逻辑**（无数据库、无 LLM）。

## 职责边界

| 本包提供 | 宿主应用提供 |
|---------|-------------|
| `AgentRoute` / `AgentRoutePlan` 类型 | Skill 关键词评分 |
| `infer_route_mode` 模式推断 | LLM 路由决策 |
| `cap_routes` handoff 上限 | DB 中 agent 启用状态 |
| `pick_route_with_fallback` | 业务专精注册表 |

## 安装

```bash
pip install agentkit-route
```

## 示例

```python
from agentkit_route import AgentRoute, RouteLimits, build_route_plan, infer_route_mode

routes = [
    AgentRoute("research", "资料检索"),
    AgentRoute("report", "撰写报告"),
]
mode = infer_route_mode("先检索资料然后写报告", len(routes), limits=RouteLimits(max_sequential_handoffs=3))
plan = build_route_plan(mode, routes, source="skill")
# plan.mode == "sequential"
```

## 更多示例

见 [examples/route_plan.py](../examples/route_plan.py)
