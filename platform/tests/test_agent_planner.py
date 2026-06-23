"""Agent 执行规划（方案 A）。"""

from __future__ import annotations

import asyncio

from app.services.agent_intent import plan_agent_tools
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    AgentExecutionPlan,
    _parse_llm_plan,
    _rule_plan_from_intent,
    build_plan_context_instruction,
    filter_tool_specs_by_plan,
    resolve_execution_plan,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)


def _tool_spec(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


def test_rule_chitchat_direct_answer():
    intent = plan_agent_tools(
        "你好",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    plan = _rule_plan_from_intent(intent)
    assert plan is not None
    assert plan.direct_answer is True
    assert plan.skip_tools == tuple(RETRIEVAL_ATOMIC_TOOLS)


def test_rule_attachment_blocks_retrieval():
    intent = plan_agent_tools(
        "总结这篇论文的方法",
        attach_count=1,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    plan = _rule_plan_from_intent(intent)
    assert plan is not None
    assert plan.direct_answer is False
    assert plan.atomic_tools == ()
    assert ATOMIC_TOOL_WEB_SEARCH in plan.skip_tools


def test_filter_removes_skipped_retrieval_and_skill_load():
    specs = [
        _tool_spec(ATOMIC_TOOL_WEB_SEARCH),
        _tool_spec(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE),
        _tool_spec("load_uploaded_skill"),
        _tool_spec("create_todo"),
    ]
    plan = AgentExecutionPlan(
        reasoning="",
        intent="查文档",
        direct_answer=False,
        atomic_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
        skip_tools=(ATOMIC_TOOL_WEB_SEARCH,),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=("检索",),
        source="test",
    )
    filtered = filter_tool_specs_by_plan(specs, plan)
    names = {s["function"]["name"] for s in filtered}
    assert ATOMIC_TOOL_KNOWLEDGE_RETRIEVE in names
    assert ATOMIC_TOOL_WEB_SEARCH not in names
    assert "load_uploaded_skill" not in names
    assert "create_todo" in names


def test_filter_always_hides_load_and_keeps_run_skill_script():
    specs = [
        _tool_spec("load_uploaded_skill"),
        _tool_spec("run_skill_script"),
        _tool_spec("create_todo"),
    ]
    plan = AgentExecutionPlan(
        reasoning="",
        intent="",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="web-page-insight",
        builtin_orchestration=None,
        steps=(),
        source="test",
    )
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "load_uploaded_skill" not in names
    assert "run_skill_script" in names
    assert "create_todo" in names


def test_plan_instruction_uploaded_skill_uses_run_script():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="分析网页",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="web-page-insight",
        builtin_orchestration=None,
        steps=("执行脚本",),
        source="test",
    )
    text = build_plan_context_instruction(plan)
    assert "run_skill_script" in text
    assert "web-page-insight" in text
    assert "勿" in text and "load_uploaded_skill" in text


def test_parse_llm_plan_distinguishes_tools_and_skills():
    data = {
        "reasoning": "需查内部制度",
        "intent": "查询碳配额流程",
        "direct_answer": False,
        "atomic_tools": ["knowledge_retrieve", "web_search"],
        "skip_tools": ["web_search"],
        "builtin_orchestration": "knowledge-research",
        "uploaded_skill": "web-page-insight",
        "steps": ["检索", "回答"],
    }
    plan = _parse_llm_plan(
        data,
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        allowed_uploaded={"web-page-insight"},
        allowed_builtin={"knowledge-research", "web-search"},
    )
    assert plan is not None
    assert plan.atomic_tools == (ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,)
    assert plan.builtin_orchestration is None
    assert plan.uploaded_skill == "web-page-insight"


def test_plan_instruction_mentions_no_load_for_builtin():
    plan = AgentExecutionPlan(
        reasoning="多路检索",
        intent="综合查资料",
        direct_answer=False,
        atomic_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration="knowledge-research",
        steps=("检索文档", "作答"),
        source="test",
    )
    text = build_plan_context_instruction(plan)
    assert "禁止" in text
    assert "load_uploaded_skill" in text
    assert "knowledge-research" in text


def test_resolve_execution_plan_rule_fast_path():
    intent = plan_agent_tools(
        "你是谁？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )

    async def _run():
        return await resolve_execution_plan(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message="你是谁？",
            intent_plan=intent,
        )

    plan = asyncio.run(_run())
    assert plan.direct_answer is True
    assert plan.source == "rule"
