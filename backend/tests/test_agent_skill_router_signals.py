"""Agent 路由信号测试。"""

from __future__ import annotations

from app.services.agent_skill_router import (
    matches_browser_intent,
    matches_search_rpa_browser_intent,
    matches_search_rpa_research_intent,
)


def test_search_rpa_routes_research_not_browser():
    assert matches_search_rpa_research_intent("搜索 rpa")
    assert matches_search_rpa_research_intent("搜索rpa")
    assert not matches_search_rpa_browser_intent("搜索 rpa")
    assert not matches_browser_intent("搜索 rpa")


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
