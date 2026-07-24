"""LLM 专精 Agent 选型解析测试。"""

from __future__ import annotations

from app.services.agent_skill_routing import (
    parse_llm_agent_route_plan,
    resolved_routes_from_agent_plan,
)
from app.services.agent_working_memory import WORKING_MEMORY_MARKER, WorkingMemory


def test_parse_llm_agent_route_plan_specialist():
    plan = parse_llm_agent_route_plan(
        {
            "orchestrator_direct": False,
            "mode": "single",
            "agents": ["carbon", "bogus"],
            "reason": "双碳政策",
        },
        allowed={"carbon", "platform", "orchestrator"},
    )
    assert plan is not None
    assert plan.agents == ["carbon"]
    resolved = resolved_routes_from_agent_plan(plan)
    assert resolved is not None
    assert resolved.items[0][0] == "carbon"
    assert "LLM" in resolved.items[0][1]


def test_parse_llm_agent_route_plan_orchestrator_direct():
    plan = parse_llm_agent_route_plan(
        {
            "orchestrator_direct": True,
            "agents": [],
            "reason": "联网新闻由调度处理",
        },
        allowed={"carbon", "platform", "orchestrator"},
    )
    assert plan is not None
    assert plan.orchestrator_direct is True
    resolved = resolved_routes_from_agent_plan(plan)
    assert resolved is not None
    assert resolved.items[0][0] == "orchestrator"


def test_parse_llm_agent_route_plan_rejects_empty_unknown():
    assert (
        parse_llm_agent_route_plan(
            {"orchestrator_direct": False, "agents": ["nope"], "reason": "x"},
            allowed={"carbon"},
        )
        is None
    )


def test_working_memory_failure_receipt_keeps_tool_facts():
    wm = WorkingMemory()
    receipt = wm.add_failure_receipt(
        agent_id="platform",
        agent_title="平台操作",
        loop_state={
            "tool_outcome_lines": ["find_skills：未找到合适技能"],
            "executed_tool_calls": [
                {"tool_name": "find_skills", "summary": "无匹配"},
            ],
        },
        reply="系统中没有可用的搜索工具",
    )
    assert "未交付" in receipt
    assert "find_skills" in receipt
    block = wm.format_prompt_block()
    assert WORKING_MEMORY_MARKER in block
    assert "失败回执" in block


def test_working_memory_observes_route_and_workflow():
    wm = WorkingMemory()
    wm.observe_route(source="skill_rag", agent_id="carbon", reason="Skill 匹配（`carbon-qa`）")
    wm.observe_stream_event(
        {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "调用工具",
                "tool": "carbon_policy",
                "status": "done",
                "detail": "已查询政策",
                "agent_id": "carbon",
            },
        }
    )
    block = wm.format_prompt_block()
    assert "路由" in block
    assert "skill_rag" in block
    assert "carbon_policy" in block


def test_resolve_agent_route_plan_uses_llm_agent_selection(monkeypatch):
    """无 Skill RAG 命中专精时，才走 LLM 读动态 agents.md 选型。"""
    import asyncio

    from app.core.phone import bootstrap_login_id
    from app.database import SessionLocal
    from app.models.org import User
    from sqlalchemy import select

    from app.core.agent.types import AgentRoute
    from app.services.agent_route_resolver import SkillPathResult, resolve_agent_route_plan
    from app.services.agent_skill_routing import ResolvedSkillRoutes

    async def fake_llm(db, message, **kwargs):
        return ResolvedSkillRoutes(
            mode="single",
            items=(("carbon", "LLM 分配（`carbon`）：双碳政策"),),
        )

    monkeypatch.setattr(
        "app.integrations.deepseek_client.is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.agent_skill_routing.llm_plan_agent_routes",
        fake_llm,
    )
    monkeypatch.setattr(
        "app.services.agent_route_resolver._resolve_hard_rule_routes",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.agent_skill_router.should_skip_kg_probe",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "app.services.agent_route_resolver.resolve_skill_path",
        lambda *a, **k: SkillPathResult(
            routes=[AgentRoute(agent_id="orchestrator", reason="无 Skill 命中")],
            source="orchestrator_default",
        ),
    )

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        plan = asyncio.run(
            resolve_agent_route_plan(db, user, "最新的双碳政策有哪些？")
        )
        assert plan.routes[0].agent_id == "carbon"
        assert plan.source == "llm_agent"
    finally:
        db.close()
