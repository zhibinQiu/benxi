"""部门成员清单 — 路由与确定性回复（禁止 LLM 编造）。"""

from unittest.mock import MagicMock

from app.services.agent_intent import needs_knowledge_retrieval
from app.services.agent_skill_router import (
    is_org_member_list_question,
    is_platform_system_data_message,
)


def test_person_org_affiliation_question():
    from app.services.agent_skill_router import (
        is_person_org_affiliation_question,
        is_platform_system_data_message,
    )

    assert is_person_org_affiliation_question("邱智斌是哪个公司的？")
    assert is_person_org_affiliation_question("张三属于哪个部门")
    assert is_person_org_affiliation_question("邱智斌是哪个部门的")
    assert is_person_org_affiliation_question("李四在哪工作")
    assert not is_person_org_affiliation_question("碳配额政策有哪些要点")
    # 人员归属走图谱，不再归类为平台账号管理
    assert not is_platform_system_data_message("邱智斌是哪个公司的？")


def test_affiliation_rule_plan_forces_kg_query():
    from app.services.agent_planner import _rule_plan_for_platform_system_data

    plan = _rule_plan_for_platform_system_data(
        MagicMock(), MagicMock(), "邱智斌是哪个公司的？"
    )
    assert plan is not None
    assert plan.intent == "查询人员所属组织"
    assert "kg_query" in plan.allowed_tools
    assert "web_search" in plan.blocked_tools


def test_platform_data_plan_when_kg_context_present():
    """有图谱规划上下文时，系统数据规则可优先于专精域。"""
    import asyncio
    from unittest.mock import patch

    from app.services.agent_intent import AgentToolPlan
    from app.services.agent_planner import resolve_execution_plan

    async def _run():
        with patch(
            "app.services.agent_planner._rule_plan_for_specialist_domain"
        ) as specialist:
            specialist.return_value = MagicMock(
                intent="股市分析", uploaded_skill="stock-deep-analysis"
            )
            plan = await resolve_execution_plan(
                MagicMock(),
                MagicMock(),
                message="邱智斌是哪个部门的",
                history=None,
                intent_plan=AgentToolPlan(
                    use_attachment=False,
                    intent_label="查询",
                    context_instruction="",
                ),
                kg_planning_context="意图标签: person_affiliation\n优先工具: kg_query\n",
                agent_id="stock",
            )
        assert plan.intent == "查询人员所属组织"
        assert "kg_query" in plan.allowed_tools
        assert plan.uploaded_skill is None

    asyncio.run(_run())


def test_org_member_list_question_detects_dept_people_query():
    assert is_org_member_list_question("咨询服务部有哪些人")
    assert is_org_member_list_question("技术部有谁")
    assert not is_org_member_list_question("碳配额政策有哪些要点")


def test_platform_system_data_excludes_dept_member_query():
    """部门成员清单走知识图谱，不算平台账号管理类系统数据。"""
    assert not is_platform_system_data_message("咨询服务部有哪些人")


def test_dept_member_query_skips_doc_retrieval():
    assert needs_knowledge_retrieval("咨询服务部有哪些人") is False


def test_format_department_members_reply_from_kg():
    """旧 PG 图谱确定性回复已迁移到 Neo4j kg_query 路径，本用例保留为占位。"""
    import pytest

    pytest.skip("format_department_members_reply 已随 Neo4j 迁移移除；归属查询走 kg_query")
