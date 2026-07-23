"""部门成员清单 — 路由与确定性回复（禁止 LLM 编造）。"""

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
    assert is_person_org_affiliation_question("李四在哪工作")
    assert not is_person_org_affiliation_question("碳配额政策有哪些要点")
    assert is_platform_system_data_message("邱智斌是哪个公司的？")


def test_affiliation_rule_plan_forces_kg_query():
    from unittest.mock import MagicMock

    from app.services.agent_planner import _rule_plan_for_platform_system_data

    plan = _rule_plan_for_platform_system_data(
        MagicMock(), MagicMock(), "邱智斌是哪个公司的？"
    )
    assert plan is not None
    assert plan.intent == "查询人员所属组织"
    assert "kg_query" in plan.allowed_tools
    assert "web_search" in plan.blocked_tools


def test_org_member_list_question_detects_dept_people_query():
    assert is_org_member_list_question("咨询服务部有哪些人")
    assert is_org_member_list_question("技术部有谁")
    assert not is_org_member_list_question("碳配额政策有哪些要点")


def test_platform_system_data_includes_dept_member_query():
    assert is_platform_system_data_message("咨询服务部有哪些人")


def test_dept_member_query_skips_doc_retrieval():
    assert needs_knowledge_retrieval("咨询服务部有哪些人") is False


def test_format_department_members_reply_from_kg():
    """旧 PG 图谱确定性回复已迁移到 Neo4j kg_query 路径，本用例保留为占位。"""
    import pytest

    pytest.skip("format_department_members_reply 已随 Neo4j 迁移移除；归属查询走 kg_query")
