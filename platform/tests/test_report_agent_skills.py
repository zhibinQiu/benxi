"""报告撰写智能体 — 类型识别与路由测试。"""

from __future__ import annotations

from app.schemas.ai_chat import AiChatMessage
from app.services.report_agent_skills import (
    build_report_workflow_intent_title,
    classify_report_skill,
    is_report_generation_message,
    is_report_page_message_acceptable,
    pick_available_report_skill,
    resolve_report_skill_for_turn,
)
from app.core.report_skill_catalog import (
    REPORT_SKILL_FEASIBILITY,
    REPORT_SKILL_REQUIREMENTS,
    REPORT_SKILL_SURVEY,
    REPORT_SKILL_TEST,
    REPORT_SKILL_WORK_PLAN,
)


def test_is_report_generation_message_positive():
    assert is_report_generation_message("请撰写一份全国碳市场行业调研报告")
    assert is_report_generation_message("生成可研报告，关于智慧园区建设")


def test_is_report_generation_message_negative():
    assert not is_report_generation_message("你好")
    assert not is_report_generation_message("画一个采购审批流程图")
    assert not is_report_generation_message("全国碳市场最新政策有哪些")


def test_classify_report_skill_types():
    assert classify_report_skill("写一份项目可研报告") == REPORT_SKILL_FEASIBILITY
    assert classify_report_skill("输出需求分析报告") == REPORT_SKILL_REQUIREMENTS
    assert classify_report_skill("整理测试报告") == REPORT_SKILL_TEST
    assert classify_report_skill("编制明年工作计划") == REPORT_SKILL_WORK_PLAN
    assert classify_report_skill("新能源汽车行业研究") == REPORT_SKILL_SURVEY


def test_pick_available_report_skill_fallback():
    available = {REPORT_SKILL_SURVEY, REPORT_SKILL_TEST}
    assert (
        pick_available_report_skill("写可研报告", available) == REPORT_SKILL_SURVEY
    )
    assert (
        pick_available_report_skill("测试报告", available) == REPORT_SKILL_TEST
    )


def test_is_report_page_message_acceptable_first_turn():
    assert is_report_page_message_acceptable("撰写一份调研报告，主题是碳市场", has_history=False)
    assert not is_report_page_message_acceptable("你好", has_history=False)
    assert is_report_page_message_acceptable("补充海外案例", has_history=True)


def test_resolve_report_skill_for_turn_keeps_first_turn_type():
    history = [
        AiChatMessage(role="user", content="撰写一份项目可研报告，主题是智慧园区"),
        AiChatMessage(role="assistant", content="## 摘要\n…"),
    ]
    available = {REPORT_SKILL_FEASIBILITY, REPORT_SKILL_SURVEY}
    assert (
        resolve_report_skill_for_turn("请扩写第三章", history, available)
        == REPORT_SKILL_FEASIBILITY
    )


def test_build_report_workflow_intent_title():
    assert (
        build_report_workflow_intent_title(
            skill_name=REPORT_SKILL_SURVEY,
            revision_intent="initial",
            has_history=False,
        )
        == "调研报告"
    )
    assert "补充与修订" in build_report_workflow_intent_title(
        skill_name=REPORT_SKILL_TEST,
        revision_intent="follow_up",
        has_history=True,
    )


def test_report_writing_quality_instruction_includes_tables_and_skill_extra():
    from app.core.report_skill_catalog import (
        REPORT_SKILL_CONSTRUCTION,
        report_writing_quality_instruction,
    )

    base = report_writing_quality_instruction()
    assert "表格" in base
    assert "mermaid" in base.lower()
    assert "车轱辘话" in base

    survey = report_writing_quality_instruction(REPORT_SKILL_SURVEY)
    assert "调研报告专要求" in survey

    construction = report_writing_quality_instruction(REPORT_SKILL_CONSTRUCTION)
    assert "建设方案专要求" in construction
