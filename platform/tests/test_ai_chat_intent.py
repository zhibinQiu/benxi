"""AI 智能体意图路由：按轮次智能决定是否检索。"""

from __future__ import annotations

import uuid

from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import (
    is_chitchat_message,
    needs_web_search,
    plan_agent_tools,
)

_is_chitchat_message = is_chitchat_message
_needs_web_search = needs_web_search
_plan_agent_tools = plan_agent_tools


def test_who_are_you_with_question_mark_is_chitchat():
    assert _is_chitchat_message("你是谁？") is True
    assert _is_chitchat_message("你是什么模型？") is True
    assert _is_chitchat_message("你好，你是谁？") is True


def test_chitchat_skips_all_tools_even_with_attachment_session():
    cases = (
        "你是谁？",
        "谢谢！",
        "在吗？",
        "你是什么模型",
        "你好，你是谁？",
        "介绍一下自己",
    )
    for message in cases:
        plan = _plan_agent_tools(
            message,
            attach_count=2,
            kb_enabled=True,
            kg_enabled=True,
            web_enabled=True,
        )
        assert plan.use_attachment is False, message
        assert plan.use_doc_retrieval is False, message
        assert plan.use_kg is False, message
        assert plan.use_web_search is False, message
        assert "日常" in plan.intent_label


def test_attachment_question_uses_attachment_only():
    plan = _plan_agent_tools(
        "这篇论文的核心方法是什么？",
        attach_count=1,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_attachment is True
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False
    assert plan.use_web_search is False
    assert "附件" in plan.intent_label


def test_attachment_with_explicit_kb_still_attachment_only():
    plan = _plan_agent_tools(
        "对比这篇论文和知识库里的碳排放政策",
        attach_count=1,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_attachment is True
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False


def test_chitchat_skips_retrieval_without_attachment():
    plan = _plan_agent_tools(
        "你好",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False


def test_business_question_defers_to_agent_tools():
    plan = _plan_agent_tools(
        "碳配额发放流程是什么？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False
    assert plan.use_web_search is False
    assert "按需" in plan.intent_label


def test_chitchat_skips_web_search():
    assert _needs_web_search("你好") is False
    assert _needs_web_search("你是谁？") is False


def test_platform_usage_skips_web_search():
    assert _needs_web_search("怎么上传文档到知识库？") is False
    plan = _plan_agent_tools(
        "怎么上传文档到知识库？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False
    assert plan.use_web_search is False


def test_followup_after_business_question_defers_to_agent_tools():
    history = [
        AiChatMessage(role="user", content="碳配额发放流程是什么？"),
        AiChatMessage(role="assistant", content="根据检索材料……"),
    ]
    plan = _plan_agent_tools(
        "继续详细说说",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
        history=history,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_web_search is False


def test_vague_message_skips_retrieval():
    plan = _plan_agent_tools(
        "今天心情不错",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_web_search is False
    assert "按需" in plan.intent_label


def test_delete_skill_removes_db_row_even_if_storage_fails():
    from unittest.mock import MagicMock, patch

    from app.services.agent_skill_service import delete_skill

    skill_id = uuid.uuid4()
    skill = MagicMock()
    skill.storage_prefix = f"skills/{skill_id}/"
    db = MagicMock()
    db.get.return_value = skill

    with patch(
        "app.services.agent_skill_service.get_object_store",
        side_effect=RuntimeError("storage unavailable"),
    ):
        delete_skill(db, skill_id)

    db.delete.assert_called_once_with(skill)
    db.commit.assert_called_once()


def test_recent_carbon_price_heuristic_still_detects_web_need():
    assert _needs_web_search("最近的碳价格是多少？") is True
    plan = _plan_agent_tools(
        "最近的碳价格是多少？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is False


def test_carbon_price_without_web_config():
    plan = _plan_agent_tools(
        "最近的碳价格是多少？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=False,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is False


def test_explicit_web_search_request_defers_to_agent_tools():
    assert _needs_web_search("帮我上网查一下欧盟碳价") is True
    plan = _plan_agent_tools(
        "帮我上网查一下欧盟碳价",
        attach_count=0,
        kb_enabled=False,
        kg_enabled=False,
        web_enabled=True,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is False


def test_policy_process_defers_retrieval_to_agent_tools():
    assert _needs_web_search("碳配额发放流程是什么？") is True
    plan = _plan_agent_tools(
        "碳配额发放流程是什么？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is False


def test_lookup_carbon_price_defers_to_agent_tools():
    assert _needs_web_search("帮我查一下碳价") is True
    plan = _plan_agent_tools(
        "帮我查一下碳价",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is False


def test_current_carbon_market_status_defers_to_agent_tools():
    assert _needs_web_search("目前全国碳市场怎么样") is True
    plan = _plan_agent_tools(
        "目前全国碳市场怎么样",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is False
