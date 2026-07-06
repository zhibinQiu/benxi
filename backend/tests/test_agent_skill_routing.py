"""Skill 驱动调度路由测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.agent_skill_routing import (
    LlmSkillRoutePlan,
    aggregate_agents_from_skills,
    agents_from_skill_selection,
    build_routing_query,
    build_skill_agent_index,
    format_routing_context_line,
    parse_failed_agents_from_text,
    parse_llm_skill_route_plan,
    pick_skill_route_scores,
    resolved_routes_from_skill_plan,
    resolve_skill_routed_agent_scores,
)
from app.services.agent_supervisor import AgentRoute, _resolve_agent_routes


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_routing_query_includes_prior_reflection():
    query = build_routing_query(
        "生成销售报表",
        prior_outcomes=["第1轮未通过：缺少导出"],
    )
    assert "销售报表" in query
    assert "缺少导出" in query


def test_parse_failed_agents():
    line = format_routing_context_line(["diagram", "platform"])
    assert parse_failed_agents_from_text(line) == ["diagram", "platform"]


def test_build_skill_agent_index_maps_research():
    db = SessionLocal()
    try:
        index = build_skill_agent_index(db)
        assert "research" in index.get("web-search", frozenset())
    finally:
        db.close()


def test_aggregate_agents_weights_primary_skills():
    from app.skills.types import SkillDefinition, SkillSource

    skills = [
        (
            4,
            SkillDefinition(
                name="web-search",
                title="联网",
                description="联网检索",
                source=SkillSource.BUILTIN,
            ),
        ),
    ]
    index = {"web-search": frozenset({"research"})}
    scores = aggregate_agents_from_skills(skills, index)
    assert scores[0].agent_id == "research"


def test_resolve_agent_routes_chitchat():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = _resolve_agent_routes(db, user, "你好")
        assert len(routes) == 1
        assert routes[0].agent_id == "orchestrator"
    finally:
        db.close()


def test_resolve_agent_routes_simple_question_stays_orchestrator():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = _resolve_agent_routes(db, user, "什么是光合作用")
        assert len(routes) == 1
        assert routes[0].agent_id == "orchestrator"
    finally:
        db.close()


def test_resolve_agent_routes_hello_after_business_question():
    from app.schemas.ai_chat import AiChatMessage

    db = SessionLocal()
    try:
        user = _admin_user(db)
        history = [
            AiChatMessage(
                role="user",
                content="这两天康宁的玻璃桥技术有没有对光模块半导体的股价产生影响？",
            ),
            AiChatMessage(
                role="assistant",
                content="康宁玻璃桥技术近期发布，对光模块板块情绪有一定影响……",
            ),
        ]
        routes = _resolve_agent_routes(db, user, "你好", chat_history=history)
        assert len(routes) == 1
        assert routes[0].agent_id == "orchestrator"
    finally:
        db.close()


def test_pick_skill_route_scores_rejects_ambiguous_weak_match():
    from app.services.agent_skill_routing import AgentRoutingScore

    scores = [
        AgentRoutingScore(agent_id="research", score=1.0, matched_skills=("web-search",)),
        AgentRoutingScore(agent_id="platform", score=1.0, matched_skills=("user-admin",)),
    ]
    assert pick_skill_route_scores(scores, query="嗯") == []
    scores_clear = [
        AgentRoutingScore(agent_id="research", score=10.0, matched_skills=("web-search",)),
        AgentRoutingScore(agent_id="report", score=1.0, matched_skills=("report-survey",)),
    ]
    assert pick_skill_route_scores(scores_clear, query="全国碳市场政策") != []


def test_resolve_agent_routes_platform_via_skills():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = _resolve_agent_routes(db, user, "列出我文档库里的文件夹")
        assert routes
        assert routes[0].agent_id == "platform"
    finally:
        db.close()


def test_skill_scores_for_research_message():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        scores = resolve_skill_routed_agent_scores(
            db, user, "全国碳市场最新政策有哪些？"
        )
        picked = pick_skill_route_scores(scores)
        assert any(s.agent_id == "research" for s in picked)
    finally:
        db.close()


def test_parse_llm_skill_route_plan_filters_unknown():
    allowed = {"web-search", "knowledge-search"}
    plan = parse_llm_skill_route_plan(
        {
            "orchestrator_direct": False,
            "mode": "single",
            "skills": ["web-search", "bogus-skill"],
            "reason": "联网调研",
        },
        allowed=allowed,
    )
    assert plan is not None
    assert plan.skills == ["web-search"]


def test_parse_llm_skill_route_plan_orchestrator_direct():
    plan = parse_llm_skill_route_plan(
        {"orchestrator_direct": True, "skills": [], "reason": "寒暄"},
        allowed=set(),
    )
    assert plan is not None
    assert plan.orchestrator_direct is True
    assert plan.skills == []


def test_agents_from_skill_selection_merges_same_agent():
    index = {
        "web-search": frozenset({"research"}),
        "knowledge-search": frozenset({"research"}),
        "user-admin": frozenset({"platform"}),
    }
    groups = agents_from_skill_selection(
        ["web-search", "knowledge-search", "user-admin"],
        index,
    )
    assert groups == [
        ("research", ["web-search", "knowledge-search"]),
        ("platform", ["user-admin"]),
    ]


def test_resolved_routes_from_skill_plan_parallel():
    index = {
        "web-search": frozenset({"research"}),
        "user-admin": frozenset({"platform"}),
    }
    plan = LlmSkillRoutePlan(
        mode="parallel",
        skills=["web-search", "user-admin"],
        reason="并行调研与平台操作",
    )
    resolved = resolved_routes_from_skill_plan(plan, index)
    assert resolved is not None
    assert resolved.mode == "parallel"
    assert [agent for agent, _ in resolved.items] == ["research", "platform"]
