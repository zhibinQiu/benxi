"""agent_execution_closure 单元测试。"""

from __future__ import annotations

from app.schemas.ai_chat import AiChatMessage
from app.services.agent_execution_closure import (
    build_skill_management_continue_nudge,
    execution_goal_satisfied,
    infer_skill_script_args,
    replan_after_missing_skill_data,
    resolve_target_uploaded_skill,
)
from app.services.agent_planner import AgentExecutionPlan


def test_infer_skill_script_args_for_beijing():
    md = 'run_skill_script(skill_name="carbon-market-price", args=["地方", "广东"])'
    assert infer_skill_script_args("北京", None, md) == ["地方", "北京"]


def test_resolve_target_uploaded_skill_from_history():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="执行发展技能",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    history = [
        AiChatMessage(role="user", content="生成 skill 爬取碳价"),
        AiChatMessage(
            role="assistant",
            content="已创建 carbon-market-price，可直接问北京碳价。",
        ),
    ]
    skill = resolve_target_uploaded_skill(
        execution_plan=plan,
        loop_state={},
        user_message="北京",
        chat_history=history,
        uploaded_names={"carbon-market-price"},
    )
    assert skill == "carbon-market-price"


def test_replan_after_missing_skill_data():
    prior = AgentExecutionPlan(
        reasoning="",
        intent="执行发展技能",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill="carbon-market-price",
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    replanned = replan_after_missing_skill_data(
        message="北京",
        history=[],
        uploaded_names={"carbon-market-price"},
        prior_plan=prior,
        loop_state={"tool_outcome_lines": ["执行 Skill：未产出有效结论"]},
    )
    assert replanned is not None
    assert replanned.source == "replan"
    assert replanned.uploaded_skill == "carbon-market-price"
    assert replanned.direct_answer is False


def test_tool_rounds_for_adaptive_pass():
    from app.services.agent_execution_closure import (
        max_adaptive_execution_passes,
        tool_rounds_for_adaptive_pass,
    )

    assert tool_rounds_for_adaptive_pass(40, 0) == 40
    assert tool_rounds_for_adaptive_pass(40, 1) == 12
    assert max_adaptive_execution_passes() >= 1


_SKILL_CREATE_MSG = (
    "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
)


def test_execution_goal_not_satisfied_after_list_only():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="创建或管理 Agent 发展技能",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    loop_state = {"tool_outcome_lines": ["Skills 目录：共 4 个技能"]}
    assert execution_goal_satisfied(
        plan, loop_state, _SKILL_CREATE_MSG, plan_has_script=None
    ) is False


def test_execution_goal_satisfied_after_create_and_run():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="创建或管理 Agent 发展技能",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    loop_state = {
        "created_uploaded_skills": ["carbon-market-price"],
        "invoked_uploaded_skills": ["carbon-market-price"],
        "tool_outcome_lines": [
            "Skills 目录：共 4 个技能",
            "创建 Skill: carbon-market-price：已创建 Skill `carbon-market-price`",
            "运行 Skill 脚本: carbon-market-price：完成",
        ],
        "last_skill_conclusion": (
            '{"数据名称":"全国碳市场","最新记录":{"收盘":83.12}}'
        ),
    }
    assert execution_goal_satisfied(
        plan, loop_state, _SKILL_CREATE_MSG, plan_has_script=True
    ) is True


def test_execution_goal_not_satisfied_create_without_run():
    plan = AgentExecutionPlan(
        reasoning="",
        intent="创建或管理 Agent 发展技能",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="rule",
    )
    loop_state = {
        "created_uploaded_skills": ["carbon-market-price"],
        "tool_outcome_lines": ["创建 Skill: carbon-market-price：已创建"],
    }
    assert execution_goal_satisfied(
        plan, loop_state, _SKILL_CREATE_MSG, plan_has_script=True
    ) is False


def test_build_skill_management_continue_nudge_after_list():
    nudge = build_skill_management_continue_nudge(
        _SKILL_CREATE_MSG,
        {"tool_outcome_lines": ["Skills 目录：共 4 个技能"]},
    )
    assert "Skills 目录" in nudge
    assert "create_uploaded_skill" in nudge
