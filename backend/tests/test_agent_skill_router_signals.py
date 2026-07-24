"""Agent 路由信号测试。"""

from __future__ import annotations

from app.services.agent_skill_router import (
    matches_browser_intent,
    matches_browser_site_search,
    matches_search_rpa_browser_intent,
    matches_search_rpa_research_intent,
)


def test_affiliation_question_falls_through_to_skill_matching_when_no_kg():
    """无图谱直答时，归属类问题不硬拦路由；同步路径兜底到调度。"""
    from unittest.mock import MagicMock, patch

    from app.services.agent_route_resolver import resolve_agent_routes_from_skills
    from app.services.agent_skill_router import is_person_org_affiliation_question

    q = "邱智斌是哪个公司的？"
    assert is_person_org_affiliation_question(q)

    with (
        patch(
            "app.services.agent_skill_routing.build_skill_agent_index",
            return_value={},
        ),
        patch(
            "app.services.agent_planner.match_uploaded_skill_for_message",
            return_value=None,
        ),
        patch(
            "app.services.agent_planner._skill_name_sets",
            return_value=set(),
        ),
    ):
        routes = resolve_agent_routes_from_skills(
            MagicMock(), MagicMock(), q, chat_history=None
        )
    assert len(routes) == 1
    assert routes[0].agent_id == "orchestrator"


def test_search_rpa_with_screenshot_routes_browser():
    assert matches_search_rpa_browser_intent("搜索 rpa并截图")
    assert matches_search_rpa_browser_intent("搜索 rpa 并截图")
    assert not matches_search_rpa_research_intent("搜索 rpa并截图")
    assert matches_browser_intent("搜索 rpa并截图")


def test_browser_rpa_agent_prefix_still_browser_with_screenshot():
    assert matches_search_rpa_browser_intent("浏览器 RPA Agent：搜索 rpa并截图")
    assert not matches_search_rpa_research_intent("浏览器 RPA Agent：搜索 rpa并截图")


def test_bing_search_carbon_with_screenshot_is_browser_intent():
    q = "bing 搜索双碳并截图"
    assert matches_browser_intent(q)
    assert matches_browser_site_search(q)


def test_hard_rules_do_not_special_case_browser_or_news():
    """浏览器/新闻不走打分式硬规则，留给 LLM 专精选型。"""
    from unittest.mock import MagicMock

    from app.services.agent_route_resolver import _resolve_hard_rule_routes

    assert _resolve_hard_rule_routes(MagicMock(), "bing 搜索双碳并截图") is None
    assert _resolve_hard_rule_routes(MagicMock(), "帮我查询最新的 AI 事件新闻") is None
