"""多智能体 Supervisor 路由与 tool 过滤测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.agent_intent import plan_agent_tools
from app.services.agent_profile_service import resolve_agent_tool_names
from app.services.agent_supervisor import (
    _best_reply_from_hops,
    _infer_route_mode,
    _parse_llm_route_plan,
    _pick_single_route_from_candidates,
    merge_hop_citations,
    resolve_agent_route,
    resolve_agent_routes,
)
from app.services.agent_tools import build_agent_tool_specs


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


def test_route_skill_management():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "帮我写一个新的 skill 抓取网页价格",
        )
        assert route.agent_id == "skill-dev"
    finally:
        db.close()


def test_route_platform_document():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "列出我文档库里的文件夹",
        )
        assert route.agent_id == "platform"
    finally:
        db.close()


def test_route_research():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        intent = plan_agent_tools(
            "全国碳市场最新政策有哪些？",
            attach_count=0,
            kb_enabled=True,
            kg_enabled=True,
            web_enabled=True,
        )
        route = resolve_agent_route(
            db,
            user,
            "全国碳市场最新政策有哪些？",
            intent_plan=intent,
        )
        assert route.agent_id == "research"
    finally:
        db.close()


def test_specialist_tool_filter():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        platform_tools = resolve_agent_tool_names(db, "platform")
        assert "list_document_folders" in platform_tools
        assert "web_search" not in platform_tools

        specs = build_agent_tool_specs(db, user, allowed_names=platform_tools)
        names = {s["function"]["name"] for s in specs}
        assert "list_document_folders" in names
        assert "web_search" not in names
    finally:
        db.close()


def test_compound_research_then_platform():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(
            db,
            user,
            "先检索知识库里的碳排放报告，然后帮我创建一个待办",
        )
        assert len(routes) == 2
        assert routes[0].agent_id == "research"
        assert routes[1].agent_id == "platform"
    finally:
        db.close()


def test_multi_domain_without_sequence_word_returns_multiple_routes():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(
            db,
            user,
            "查知识库里的碳报告并创建待办",
        )
        assert len(routes) == 2
        assert routes[0].agent_id == "research"
        assert routes[1].agent_id == "platform"
        assert _infer_route_mode(
            "查知识库里的碳报告并创建待办", len(routes)
        ) == "sequential"
    finally:
        db.close()


def test_parallel_mode_with_simultaneous_keyword():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(
            db,
            user,
            "检索知识库里的碳政策，同时列出我的待办事项",
        )
        assert len(routes) >= 2
        assert _infer_route_mode(
            "检索知识库里的碳政策，同时列出我的待办事项", len(routes)
        ) == "parallel"
    finally:
        db.close()


def test_multi_route_defaults_to_sequential_without_parallel_keyword():
    assert _infer_route_mode("先A然后B", 2) == "sequential"
    assert _infer_route_mode("查报告并创建待办", 2) == "sequential"


def test_merge_hop_citations_dedupes():
    a = [{"url": "https://a", "title": "A", "snippet": "x"}]
    b = [{"url": "https://a", "title": "A", "snippet": "x"}, {"url": "https://b", "title": "B"}]
    merged = merge_hop_citations([a, b])
    assert len(merged) == 2
    urls = {item["url"] for item in merged}
    assert urls == {"https://a", "https://b"}


def test_parse_llm_route_plan():
    db = SessionLocal()
    try:
        plan = _parse_llm_route_plan(
            db,
            {
                "mode": "parallel",
                "agents": ["research", "platform"],
                "reason": "同时检索与平台操作",
            },
        )
        assert plan is not None
        assert plan.mode == "parallel"
        assert [r.agent_id for r in plan.routes] == ["research", "platform"]
    finally:
        db.close()


def test_ambiguous_multi_domain_yields_sequential_routes():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(
            db,
            user,
            "查知识库里的碳报告并创建待办",
        )
        assert len(routes) == 2
        picked = _pick_single_route_from_candidates(
            routes,
            None,
        )
        assert picked.agent_id == "platform"
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


def test_best_reply_from_hops_uses_last_non_empty():
    hops = [
        {"reply": "第一步结果"},
        {"reply": ""},
    ]
    assert _best_reply_from_hops(hops) == "第一步结果"


def test_pick_single_route_prefers_platform_on_platform_intent():
    from app.services.agent_supervisor import AgentRoute
    from app.services.agent_intent import AgentToolPlan

    intent = AgentToolPlan(
        use_attachment=False,
        use_doc_retrieval=False,
        use_kg=False,
        use_web_search=False,
        intent_label="解答平台使用问题",
        context_instruction="",
    )
    picked = _pick_single_route_from_candidates(
        [
            AgentRoute(agent_id="research", reason="检索"),
            AgentRoute(agent_id="platform", reason="平台"),
        ],
        intent,
    )
    assert picked.agent_id == "platform"
