"""Agent 执行规划（方案 A）。"""

from __future__ import annotations

import asyncio

from app.services.agent_intent import plan_agent_tools
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    AgentExecutionPlan,
    _parse_llm_plan,
    _planning_system_prompt,
    _rule_plan_for_chitchat,
    _rule_plan_for_skill_management,
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


def test_rule_chitchat_direct_answer_fast_path():
    intent = plan_agent_tools(
        "你好",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert _rule_plan_from_intent(intent) is None
    plan = _rule_plan_for_chitchat("你好")
    assert plan is not None
    assert plan.direct_answer is True
    assert plan.source == "rule"
    assert intent.intent_label == "处理用户请求"


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
    text = build_plan_context_instruction(plan, uploaded_skill_has_script=True)
    assert "run_skill_script" in text
    assert "web-page-insight" in text
    assert "勿 load" in text


def test_plan_instruction_instruction_only_skill_no_run_script():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="画流程图",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="mermaid-diagram",
        builtin_orchestration=None,
        steps=("按 SKILL.md 输出 mermaid",),
        source="test",
    )
    text = build_plan_context_instruction(plan, uploaded_skill_has_script=False)
    assert "mermaid-diagram" in text
    assert "勿" in text and "run_skill_script" in text
    assert "mermaid" in text


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
    assert "勿 load" in text
    assert "knowledge-research" in text


def test_rule_skill_management_skips_screenshot_by_default():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert "browser_screenshot" in plan.skip_tools


def test_rule_skill_management_allows_screenshot_when_asked():
    msg = "生成一个 skill 爬取碳价，并截图给我看一下页面"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert "browser_screenshot" not in plan.skip_tools


def test_filter_removes_browser_screenshot_for_skill_management_plan():
    specs = [
        _tool_spec("browser_navigate"),
        _tool_spec("browser_snapshot"),
        _tool_spec("browser_screenshot"),
        _tool_spec("create_uploaded_skill"),
    ]
    plan = _rule_plan_for_skill_management(
        "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    )
    assert plan is not None
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "browser_navigate" in names
    assert "browser_snapshot" in names
    assert "browser_screenshot" not in names
    assert "create_uploaded_skill" in names


def test_rule_skill_management_never_direct_answer():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert plan.direct_answer is False
    assert plan.source == "rule"
    assert "create_uploaded_skill" in " ".join(plan.steps)
    assert "list_agent_skills" in plan.steps[0]
    assert "澄清" in " ".join(plan.steps)
    assert "run_skill_script" in " ".join(plan.steps)


def test_coerce_skill_management_overrides_direct_answer_llm_plan():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    parsed = _parse_llm_plan(
        {
            "reasoning": "可直接说明做法",
            "intent": "生成爬取碳市场价格的发展技能",
            "direct_answer": True,
            "atomic_tools": [],
            "skip_tools": list(RETRIEVAL_ATOMIC_TOOLS),
            "steps": [],
        },
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        allowed_uploaded=set(),
        allowed_builtin=set(),
    )
    assert parsed is not None
    assert parsed.direct_answer is True
    from app.services.agent_planner import _coerce_skill_management_plan

    fixed = _coerce_skill_management_plan(msg, parsed)
    assert fixed.direct_answer is False
    assert "browser_screenshot" in fixed.skip_tools


def test_planning_system_prompt_mentions_skill_creation():
    from app.services.agent_planner import _skill_management_plan_instruction

    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        builtin_names=set(),
        uploaded_names=set(),
    )
    assert "任务规划器" in text
    assert "direct_answer" in text
    assert "main.py" in _skill_management_plan_instruction()


def test_skill_management_plan_instruction_injected():
    from app.services.agent_planner import build_plan_context_instruction

    plan = _rule_plan_for_skill_management(
        "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    )
    assert plan is not None
    text = build_plan_context_instruction(plan)
    assert "先调研" in text
    assert "main.py" in text or "create" in text


def test_planning_system_prompt_includes_kg_disambiguation_when_requested():
    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        builtin_names={"knowledge-research"},
        uploaded_names=set(),
        include_kg_reference=True,
    )
    assert "消歧" in text
    assert "kg_query" in text


def test_planning_system_prompt_omits_kg_block_by_default():
    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        builtin_names=set(),
        uploaded_names=set(),
    )
    assert "消歧" not in text


def test_rule_simple_fetch_uses_web_search_not_skill():
    from app.services.agent_planner import (
        _rule_plan_for_simple_fetch,
        match_uploaded_skill_for_message,
    )

    plan = _rule_plan_for_simple_fetch("帮我查全国碳市场最新价格")
    assert plan is not None
    assert plan.uploaded_skill is None
    assert ATOMIC_TOOL_WEB_SEARCH in plan.atomic_tools

    assert _rule_plan_for_simple_fetch(
        "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    ) is None

    skill = match_uploaded_skill_for_message(
        "北京碳价多少",
        None,
        uploaded_names={"carbon-market-price"},
    )
    assert skill == "carbon-market-price"
    assert _rule_plan_for_simple_fetch(
        "北京碳价多少",
        uploaded_names={"carbon-market-price"},
    ) is None


def test_skill_first_plan_before_web_search():
    from app.services.agent_planner import _rule_plan_for_uploaded_skill_followup

    plan = _rule_plan_for_uploaded_skill_followup(
        "查一下广东最新碳价",
        None,
        {"carbon-market-price"},
    )
    assert plan is not None
    assert plan.uploaded_skill == "carbon-market-price"
    assert ATOMIC_TOOL_WEB_SEARCH not in plan.atomic_tools


def test_rule_platform_system_data_requires_list_users():
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.services.agent_planner import _rule_plan_for_platform_system_data
    from app.services.skill_chat_service import ATOMIC_TOOL_KNOWLEDGE_RETRIEVE

    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        plan = _rule_plan_for_platform_system_data(db, admin, "系统中有哪些用户")
        assert plan is not None
        assert plan.direct_answer is False
        assert any("list_users" in step for step in plan.steps)
        assert ATOMIC_TOOL_KNOWLEDGE_RETRIEVE in plan.skip_tools
    finally:
        db.close()


def test_coerce_atomic_first_clears_unrequested_skill():
    from app.services.agent_planner import _coerce_atomic_first_plan

    plan = AgentExecutionPlan(
        reasoning="",
        intent="查询",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="carbon-price-scraper",
        builtin_orchestration=None,
        steps=(),
        source="llm",
    )
    fixed = _coerce_atomic_first_plan("查最新碳价", plan)
    assert fixed.uploaded_skill is None
    assert ATOMIC_TOOL_WEB_SEARCH in fixed.atomic_tools


def test_filter_hides_run_skill_script_without_uploaded_skill():
    specs = [_tool_spec("run_skill_script"), _tool_spec("web_search")]
    plan = AgentExecutionPlan(
        reasoning="",
        intent="查询",
        direct_answer=False,
        atomic_tools=(ATOMIC_TOOL_WEB_SEARCH,),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "run_skill_script" not in names


def test_resolve_execution_plan_attachment_rule_fast_path():
    intent = plan_agent_tools(
        "总结这篇论文的方法",
        attach_count=1,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )

    async def _run():
        return await resolve_execution_plan(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message="总结这篇论文的方法",
            intent_plan=intent,
        )

    plan = asyncio.run(_run())
    assert plan.direct_answer is False
    assert plan.source == "rule"
    assert "附件" in plan.intent


def test_rule_uploaded_skill_followup_after_carbon_skill_creation():
    from app.schemas.ai_chat import AiChatMessage
    from app.services.agent_planner import _rule_plan_for_uploaded_skill_followup

    history = [
        AiChatMessage(
            role="user",
            content="生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。",
        ),
        AiChatMessage(
            role="assistant",
            content="已为您创建 carbon-market-price 技能，可直接用自然语言查询各地碳价。",
        ),
    ]
    plan = _rule_plan_for_uploaded_skill_followup(
        "北京",
        history,
        {"carbon-market-price"},
    )
    assert plan is not None
    assert plan.uploaded_skill == "carbon-market-price"
    assert plan.direct_answer is False
