"""人员归属路由：应走 orchestrator + kg_query，禁止 platform/list_users。"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.agent_planner import (
    ATOMIC_TOOL_KG_QUERY,
    _rule_plan_for_platform_system_data,
    filter_tool_specs_by_plan,
)
from app.services.agent_route_resolver import _resolve_hard_rule_routes
from app.services.agent_skill_router import is_platform_system_data_message


def test_affiliation_not_platform_system_data():
    q = "邱智斌是哪个部门的？"
    assert is_platform_system_data_message(q) is False


def test_affiliation_hard_routes_to_orchestrator():
    db = MagicMock()
    routes = _resolve_hard_rule_routes(db, "邱智斌是哪个部门的？")
    assert routes is not None
    assert len(routes) == 1
    assert routes[0].agent_id == "orchestrator"
    assert "知识图谱" in (routes[0].reason or "") or "本体" in (routes[0].reason or "")


def test_affiliation_rule_plan_allows_only_kg_query():
    db = MagicMock()
    user = MagicMock()
    plan = _rule_plan_for_platform_system_data(db, user, "邱智斌是哪个部门的？")
    assert plan is not None
    assert plan.allowed_tools == (ATOMIC_TOOL_KG_QUERY,)
    assert "list_users" not in " ".join(plan.steps)


def test_filter_specs_retrieval_allowlist_when_kg_only():
    from app.services.agent_planner import _make_plan

    plan = _make_plan(
        reasoning="t",
        intent="查询人员所属组织",
        allowed_tools=(ATOMIC_TOOL_KG_QUERY,),
        blocked_tools=(),
        steps=("kg_query",),
    )
    specs = [
        {"function": {"name": "kg_query"}},
        {"function": {"name": "ontology_query"}},
        {"function": {"name": "web_search"}},
        {"function": {"name": "invoke_context_subagent"}},
    ]
    out = filter_tool_specs_by_plan(specs, plan)
    names = {str((s.get("function") or {}).get("name")) for s in out}
    assert "kg_query" in names
    assert "web_search" not in names  # blocked via retrieval allowlist
    assert "invoke_context_subagent" in names


def test_platform_whitelist_excludes_user_dept_sql_tools():
    from app.core.tool_skill_taxonomy import AGENT_TOOL_WHITELIST

    mounted = set(AGENT_TOOL_WHITELIST["platform"]["atomic"]) | set(
        AGENT_TOOL_WHITELIST["platform"]["runtime"]
    )
    for tool in (
        "list_users",
        "create_user",
        "update_user",
        "delete_user",
        "list_departments",
        "create_department",
        "update_department",
        "delete_department",
    ):
        assert tool not in mounted
