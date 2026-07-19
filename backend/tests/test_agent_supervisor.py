"""多智能体 Supervisor 路由与 tool 过滤测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.agent_intent import plan_agent_tools
from app.services.agent_profile_service import resolve_agent_tool_names
from app.services.agent_supervisor import (
    AgentRoutePlan,
    _best_reply_from_hops,
    _infer_route_mode,
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


def test_route_report_survey():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "请撰写一份关于 AI 在制造业质检场景的应用调研报告",
        )
        assert route.agent_id == "report"
    finally:
        db.close()


def test_route_report_feasibility():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "帮我生成智慧园区项目的可研报告",
        )
        assert route.agent_id == "report"
    finally:
        db.close()


def test_route_diagram_mindmap():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "帮我生成把大象装进冰箱的思维导图",
        )
        assert route.agent_id == "diagram"
    finally:
        db.close()


def test_route_diagram_flowchart():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(
            db,
            user,
            "画一个采购审批流程图",
        )
        assert route.agent_id == "diagram"
    finally:
        db.close()


def test_specialist_tool_filter():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        from app.services.agent_profile_service import (
            resolve_agent_internal_atomic_tools,
            resolve_agent_runtime_tool_names,
            resolve_agent_skill_names,
        )
        from app.services.agent_skill_runtime import build_agent_runtime_tool_specs

        platform_internal = resolve_agent_internal_atomic_tools(db, "platform")
        assert "list_document_folders" in platform_internal
        assert "list_users" in platform_internal
        assert "list_departments" in platform_internal
        assert "kg_query" in platform_internal

        platform_runtime = resolve_agent_runtime_tool_names(db, "platform")
        assert "invoke_skill" in platform_runtime
        assert "list_document_folders" not in platform_runtime

        skills = resolve_agent_skill_names(db, "platform")
        specs = build_agent_runtime_tool_specs(
            db, user, agent_id="platform", allowed_skill_names=skills
        )
        names = {s["function"]["name"] for s in specs}
        assert "invoke_skill" in names
        assert "list_document_folders" not in names

        research_internal = resolve_agent_internal_atomic_tools(db, "research")
        assert "knowledge_retrieve" in research_internal
        assert "search_documents_by_name" in research_internal
        assert "web_search" in research_internal
        assert "list_document_folders" not in research_internal
        assert "list_users" not in research_internal
    finally:
        db.close()


def test_route_platform_system_user_list():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        from app.services.agent_profile_service import resolve_agent_internal_atomic_tools

        route = resolve_agent_route(db, user, "系统中有哪些用户")
        assert route.agent_id == "platform"
        internal = resolve_agent_internal_atomic_tools(db, route.agent_id)
        assert "list_users" in internal
        assert "kg_query" in internal
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
        agent_ids = {r.agent_id for r in routes}
        assert len(routes) >= 2
        assert "research" in agent_ids
        assert "platform" in agent_ids
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
        agent_ids = {r.agent_id for r in routes}
        assert len(routes) >= 2
        assert "research" in agent_ids
        assert "platform" in agent_ids
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


def test_ambiguous_multi_domain_yields_sequential_routes():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        routes = resolve_agent_routes(
            db,
            user,
            "查知识库里的碳报告并创建待办",
        )
        agent_ids = {r.agent_id for r in routes}
        assert len(routes) >= 2
        assert "research" in agent_ids
        assert "platform" in agent_ids
        picked = _pick_single_route_from_candidates(routes, None)
        assert picked.agent_id in agent_ids
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


def test_short_market_question_routes_when_skills_match():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(db, user, "韩国股市熔断对A股半导体影响？")
        assert route.agent_id in ("research", "orchestrator")
    finally:
        db.close()


def test_best_reply_from_hops_uses_last_non_empty():
    hops = [
        {"reply": "第一步结果"},
        {"reply": ""},
    ]
    assert _best_reply_from_hops(hops) == "第一步结果"


def test_pick_single_route_returns_first_candidate():
    from app.services.agent_supervisor import AgentRoute

    picked = _pick_single_route_from_candidates(
        [
            AgentRoute(agent_id="research", reason="检索"),
            AgentRoute(agent_id="platform", reason="平台"),
        ],
        None,
    )
    assert picked.agent_id == "research"


def test_baidu_search_with_screenshot_routes_rpa():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        from app.services.agent_supervisor import _resolve_agent_routes

        routes = _resolve_agent_routes(db, user, "百度搜索双碳并查看结果截图。")
        assert routes
        assert routes[0].agent_id == "orchestrator"
    finally:
        db.close()


def test_baidu_screenshot_prefers_rpa_with_skill_history():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        from app.schemas.ai_chat import AiChatMessage
        from app.services.agent_supervisor import _resolve_agent_routes

        history = [
            AiChatMessage(
                role="assistant",
                content="已创建 Skill `tanshichang-scraper`，可用 run_skill_script 验证。",
            )
        ]
        routes = _resolve_agent_routes(
            db,
            user,
            "百度搜索双碳并查看结果截图",
            chat_history=history,
        )
        assert routes
        assert routes[0].agent_id == "orchestrator"
    finally:
        db.close()


