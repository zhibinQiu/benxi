"""Agent 路由信号测试。"""

from __future__ import annotations

from app.services.agent_skill_router import (
    matches_browser_intent,
    matches_search_rpa_browser_intent,
    matches_search_rpa_research_intent,
)


def test_affiliation_question_not_hard_routed_to_platform():
    """归属类问题不做路由硬拦截；仅显式指定智能体/技能/工具时才硬拦。"""
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
        patch(
            "app.services.agent_route_resolver._match_agent_directly",
            return_value=None,
        ),
        patch(
            "app.services.agent_skill_routing.resolve_skill_routed_agent_scores",
            return_value=[],
        ),
        patch(
            "app.services.agent_skill_routing.pick_skill_route_scores",
            return_value=[],
        ),
    ):
        routes = resolve_agent_routes_from_skills(
            MagicMock(), MagicMock(), q, chat_history=None
        )
    assert len(routes) == 1
    # 无显式指定时走调度兜底，不得因问题类型硬拦到 platform
    assert routes[0].agent_id == "orchestrator"


def test_search_rpa_with_screenshot_routes_browser():
    assert matches_search_rpa_browser_intent("搜索 rpa并截图")
    assert matches_search_rpa_browser_intent("搜索 rpa 并截图")
    assert not matches_search_rpa_research_intent("搜索 rpa并截图")
    assert matches_browser_intent("搜索 rpa并截图")


def test_browser_rpa_agent_prefix_still_browser_with_screenshot():
    assert matches_search_rpa_browser_intent("浏览器 RPA Agent：搜索 rpa并截图")
    assert not matches_search_rpa_research_intent("浏览器 RPA Agent：搜索 rpa并截图")


def test_search_rpa_supervisor_routes():
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.services.agent_supervisor import _resolve_agent_routes

    db = SessionLocal()
    try:
        user = db.scalar(select(User).limit(1))
        assert user is not None
        research_routes = _resolve_agent_routes(db, user, "搜索 rpa")
        assert research_routes[0].agent_id == "orchestrator"
        browser_routes = _resolve_agent_routes(db, user, "搜索 rpa并截图")
        assert browser_routes[0].agent_id == "orchestrator"
    finally:
        db.close()
