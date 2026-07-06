"""agentkit-route 纯逻辑测试。"""

from agentkit_route import AgentRoute, RouteLimits, build_route_plan, cap_routes, infer_route_mode


def test_infer_sequential():
    mode = infer_route_mode("先搜索然后写报告", 2)
    assert mode == "sequential"


def test_cap_routes():
    routes = [AgentRoute("a", "1"), AgentRoute("b", "2"), AgentRoute("c", "3")]
    capped = cap_routes("sequential", routes, limits=RouteLimits(max_sequential_handoffs=2))
    assert len(capped) == 2


def test_build_route_plan_single_when_capped_one():
    plan = build_route_plan("sequential", [AgentRoute("a", "1")], source="test")
    assert plan.mode == "single"
