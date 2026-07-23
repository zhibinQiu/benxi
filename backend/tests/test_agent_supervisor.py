"""多智能体 Supervisor 路由与 tool 过滤测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.agentkit.aip.orchestration import best_reply_from_hops, merge_hop_citations
from app.agentkit.route.routing import infer_route_mode
from app.core.agent.types import AgentRoute
from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.agent_route_resolver import (
    pick_single_route_from_candidates,
    resolve_agent_route,
    resolve_agent_routes,
)


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_route_chitchat_to_orchestrator():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(db, user, "你好")
        assert route.agent_id == "orchestrator"
    finally:
        db.close()


def test_route_returns_single_candidate():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(db, user, "列出我文档库里的文件夹")
        assert len(routes) == 1
        assert routes[0].agent_id
        assert routes[0].reason
    finally:
        db.close()


def test_route_platform_system_user_list_nonempty():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(db, user, "系统中有哪些用户")
        assert route.agent_id in ("platform", "orchestrator")
    finally:
        db.close()


def test_simple_math_routes_to_orchestrator_not_research():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(db, user, "1+1等于多少")
        assert route.agent_id == "orchestrator"
    finally:
        db.close()


def test_multi_route_defaults_to_sequential_without_parallel_keyword():
    assert infer_route_mode("先A然后B", 2) == "sequential"
    assert infer_route_mode("查报告并创建待办", 2) == "sequential"


def test_merge_hop_citations_dedupes():
    a = [{"url": "https://a", "title": "A", "snippet": "x"}]
    b = [{"url": "https://a", "title": "A", "snippet": "x"}, {"url": "https://b", "title": "B"}]
    merged = merge_hop_citations([a, b])
    assert len(merged) == 2
    urls = {item["url"] for item in merged}
    assert urls == {"https://a", "https://b"}


def test_best_reply_from_hops_uses_last_non_empty():
    hops = [
        {"reply": "第一步结果"},
        {"reply": ""},
    ]
    assert best_reply_from_hops(hops) == "第一步结果"


def test_pick_single_route_returns_first_candidate():
    picked = pick_single_route_from_candidates(
        [
            AgentRoute(agent_id="research", reason="检索"),
            AgentRoute(agent_id="platform", reason="平台"),
        ],
    )
    assert picked.agent_id == "research"


def test_specialist_runtime_builds_tool_specs():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        from app.services.agent_profile_service import resolve_agent_skill_names
        from app.services.agent_skill_runtime import build_agent_runtime_tool_specs

        skills = resolve_agent_skill_names(db, "platform")
        specs = build_agent_runtime_tool_specs(
            db, user, agent_id="platform", allowed_skill_names=skills
        )
        assert isinstance(specs, list)
        assert all("function" in s for s in specs)
    finally:
        db.close()
