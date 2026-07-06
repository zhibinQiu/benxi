"""agentkit-route 路由分数过滤测试。"""

from agentkit_route import AgentRoute, filter_routes_by_agent_scores


def test_filter_routes_by_agent_scores():
    routes = [
        AgentRoute("a", "1"),
        AgentRoute("b", "2"),
        AgentRoute("c", "3"),
    ]
    scores = {"a": 10.0, "b": 8.0, "c": 1.0}
    filtered = filter_routes_by_agent_scores(routes, scores, top_score=10.0)
    assert len(filtered) == 2
    assert filtered[0].agent_id == "a"
    assert filtered[1].agent_id == "b"
