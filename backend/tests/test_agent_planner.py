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
    execution_plan_summary_for_ui,
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
    )
    plan = _rule_plan_from_intent(intent)
    assert plan is not None
    assert plan.direct_answer is False
    assert plan.allowed_tools == ()
    assert ATOMIC_TOOL_WEB_SEARCH not in plan.blocked_tools


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
        allowed_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
        blocked_tools=(ATOMIC_TOOL_WEB_SEARCH,),
        uploaded_skill=None,
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
        allowed_tools=(),
        blocked_tools=(),
        uploaded_skill="web-page-insight",
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
        allowed_tools=(),
        blocked_tools=(),
        uploaded_skill="web-page-insight",
        steps=("执行脚本",),
        source="test",
    )
    text = build_plan_context_instruction(plan, uploaded_skill_has_script=True)
    assert "执行技能" in text
    assert "web-page-insight" in text


def test_plan_instruction_instruction_only_skill_no_run_script():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="画流程图",
        direct_answer=False,
        allowed_tools=(),
        blocked_tools=(),
        uploaded_skill="mermaid-diagram",
        steps=("按 SKILL.md 输出 mermaid",),
        source="test",
    )
    text = build_plan_context_instruction(plan, uploaded_skill_has_script=False)
    assert "mermaid-diagram" in text


def test_parse_llm_plan_distinguishes_tools_and_skills():
    data = {
        "reasoning": "需查内部制度",
        "intent": "查询碳配额流程",
        "direct_answer": False,
        "allowed_tools": ["knowledge_retrieve", "web_search"],
        "blocked_tools": ["web_search"],
        "uploaded_skill": "web-page-insight",
        "steps": ["检索", "回答"],
    }
    plan = _parse_llm_plan(
        data,
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        allowed_uploaded={"web-page-insight"},
    )
    assert plan is not None
    assert plan.allowed_tools == (ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,)
    assert plan.uploaded_skill == "web-page-insight"


def test_rule_skill_management_skips_screenshot_by_default():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert "browser_screenshot" in plan.blocked_tools


def test_rule_skill_management_allows_screenshot_when_asked():
    msg = "生成一个 skill 爬取碳价，并截图给我看一下页面"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert "browser_screenshot" not in plan.blocked_tools


def test_filter_hides_list_and_load_for_skill_management_plan():
    specs = [
        _tool_spec("list_agent_skills"),
        _tool_spec("load_uploaded_skill"),
        _tool_spec("create_skill"),
        _tool_spec("run_skill_script"),
    ]
    plan = _rule_plan_for_skill_management("帮我创建一个 skill 爬碳价")
    assert plan is not None
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "list_agent_skills" not in names
    assert "load_uploaded_skill" not in names
    assert "create_skill" in names
    assert "run_skill_script" in names


def test_filter_removes_browser_screenshot_for_skill_management_plan():
    specs = [
        _tool_spec("browser_navigate"),
        _tool_spec("browser_snapshot"),
        _tool_spec("browser_screenshot"),
        _tool_spec("create_skill"),
    ]
    plan = _rule_plan_for_skill_management(
        "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    )
    assert plan is not None
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "browser_navigate" in names
    assert "browser_snapshot" in names
    assert "browser_screenshot" not in names
    assert "create_skill" in names


def test_rule_skill_management_never_direct_answer():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    assert plan.direct_answer is False
    assert plan.source == "rule"
    assert "create_skill" in " ".join(plan.steps)
    assert "list_agent_skills" not in " ".join(plan.steps)
    assert "invoke_context_subagent" in " ".join(plan.steps)
    assert "澄清" in " ".join(plan.steps)
    assert "run_skill_script" in " ".join(plan.steps)


def test_skill_management_summary_for_ui_hides_internal_tools():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    plan = _rule_plan_for_skill_management(msg)
    assert plan is not None
    summary = execution_plan_summary_for_ui(plan)
    assert "list_agent_skills" not in summary
    assert "browser_snapshot" not in summary
    assert "create_skill" not in summary
    assert "技能开发" in summary
    assert "创建" in summary or "调研" in summary


def test_coerce_skill_management_overrides_direct_answer_llm_plan():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    parsed = _parse_llm_plan(
        {
            "reasoning": "可直接说明做法",
            "intent": "生成爬取碳市场价格的发展技能",
            "direct_answer": True,
            "allowed_tools": [],
            "blocked_tools": list(RETRIEVAL_ATOMIC_TOOLS),
            "steps": [],
        },
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        allowed_uploaded=set(),
    )
    assert parsed is not None
    assert parsed.direct_answer is True
    from app.services.agent_planner import _coerce_skill_management_plan

    fixed = _coerce_skill_management_plan(msg, parsed)
    assert fixed.direct_answer is False
    assert "browser_screenshot" in fixed.blocked_tools


def test_planning_system_prompt_mentions_skill_creation():
    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        uploaded_names=set(),
    )
    assert "任务规划器" in text
    assert "direct_answer" in text


def test_skill_management_plan_instruction_injected():
    from app.services.agent_planner import build_plan_context_instruction

    plan = _rule_plan_for_skill_management(
        "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    )
    assert plan is not None
    text = build_plan_context_instruction(plan)
    assert "invoke_context_subagent" in text
    assert "create_skill" in text


def test_planning_system_prompt_includes_kg_disambiguation_when_requested():
    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        uploaded_names=set(),
        include_kg_reference=True,
    )
    assert "消歧" in text
    assert "kg_query" in text


def test_planning_system_prompt_omits_kg_block_by_default():
    text = _planning_system_prompt(
        allowed_atomic=set(RETRIEVAL_ATOMIC_TOOLS),
        uploaded_names=set(),
    )
    assert "消歧" not in text




def test_skill_first_plan_before_web_search():
    from unittest.mock import MagicMock, patch

    from app.schemas.ai_chat import AiChatMessage
    from app.services.agent_planner import _rule_plan_for_uploaded_skill_followup

    history = [
        AiChatMessage(
            role="user",
            content="生成 skill 爬取行情数据",
        ),
        AiChatMessage(
            role="assistant",
            content="已为您创建 carbon-market-price 技能。",
        ),
    ]
    with patch(
        "app.services.agent_skill_service.uploaded_skill_has_script",
        return_value=True,
    ):
        plan = _rule_plan_for_uploaded_skill_followup(
            MagicMock(),
            MagicMock(),
            "广东",
            history,
            {"carbon-market-price"},
        )
    assert plan is not None
    assert plan.uploaded_skill == "carbon-market-price"
    assert ATOMIC_TOOL_WEB_SEARCH not in plan.allowed_tools
    assert any("kind=use" in s for s in plan.steps)


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
        plan = _rule_plan_for_platform_system_data(db, admin, "用户管理列表")
        assert plan is not None
        assert plan.direct_answer is False
        assert any("invoke_skill" in step and "list_users" in step for step in plan.steps)
        assert ATOMIC_TOOL_KNOWLEDGE_RETRIEVE in plan.blocked_tools
    finally:
        db.close()


def test_coerce_skill_first_clears_unrequested_skill():
    from app.services.agent_planner import _coerce_skill_first_plan

    plan = AgentExecutionPlan(
        reasoning="",
        intent="查询",
        direct_answer=False,
        allowed_tools=(),
        blocked_tools=(),
        uploaded_skill="carbon-price-scraper",
        steps=(),
        source="llm",
    )
    fixed = _coerce_skill_first_plan("查最新碳价", plan)
    assert fixed.uploaded_skill is None


def test_filter_hides_run_skill_script_without_uploaded_skill():
    specs = [_tool_spec("run_skill_script"), _tool_spec("web_search")]
    plan = AgentExecutionPlan(
        reasoning="",
        intent="查询",
        direct_answer=False,
        allowed_tools=(ATOMIC_TOOL_WEB_SEARCH,),
        blocked_tools=(),
        uploaded_skill=None,
        steps=(),
        source="rule",
    )
    names = {s["function"]["name"] for s in filter_tool_specs_by_plan(specs, plan)}
    assert "run_skill_script" not in names


def test_resolve_execution_plan_attachment_rule_fast_path():
    intent = plan_agent_tools(
        "总结这篇论文的方法",
        attach_count=1,
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
    from unittest.mock import MagicMock, patch

    with patch(
        "app.services.agent_skill_service.uploaded_skill_has_script",
        return_value=True,
    ):
        plan = _rule_plan_for_uploaded_skill_followup(
            MagicMock(),
            MagicMock(),
            "北京",
            history,
            {"carbon-market-price"},
        )
    assert plan is not None
    assert plan.uploaded_skill == "carbon-market-price"
    assert plan.direct_answer is False
    assert any("kind=use" in s for s in plan.steps)


def test_hello_after_stock_question_does_not_inherit_carbon_skill():
    from app.schemas.ai_chat import AiChatMessage
    from app.services.agent_planner import match_uploaded_skill_for_message

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
    skill = match_uploaded_skill_for_message(
        "你好",
        history,
        uploaded_names={"carbon-market-price", "carbon-forecast"},
    )
    assert skill is None




def test_resolve_execution_plan_skips_global_report_when_agent_is_platform():
    from sqlalchemy import select

    from app.core.phone import bootstrap_login_id
    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        assert user is not None
        msg = "请撰写一份关于 AI 在制造业质检场景的应用调研报告"

        async def _run():
            return await resolve_execution_plan(
                db,
                user,
                message=msg,
                agent_id="platform",
            )

        plan = asyncio.run(_run())
        assert plan.source == "specialist"
        assert plan.intent == "平台操作"
        assert plan.uploaded_skill is None
    finally:
        db.close()
