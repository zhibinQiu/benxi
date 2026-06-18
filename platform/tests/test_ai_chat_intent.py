"""AI 智能体意图路由：按轮次智能决定是否检索。"""

from __future__ import annotations

from app.schemas.ai_chat import AiChatMessage
from app.services.ai_chat_service import (
    _is_chitchat_message,
    _needs_web_search,
    _plan_agent_tools,
)


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
        assert "日常" in plan.intent_label


def test_attachment_question_skips_knowledge_retrieval():
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
    assert "附件" in plan.intent_label


def test_attachment_with_explicit_kb_request_uses_retrieval():
    plan = _plan_agent_tools(
        "对比这篇论文和知识库里的碳排放政策",
        attach_count=1,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_attachment is True
    assert plan.use_doc_retrieval is True
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


def test_business_question_retrieves():
    plan = _plan_agent_tools(
        "碳配额发放流程是什么？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is True
    assert plan.use_kg is True


def test_platform_usage_skips_retrieval():
    plan = _plan_agent_tools(
        "怎么上传文档到知识库？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_doc_retrieval is False
    assert plan.use_kg is False


def test_followup_after_business_question_retrieves():
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
    assert plan.use_doc_retrieval is True


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
    assert plan.intent_label == "直接回答"


def test_recent_carbon_price_uses_web_search():
    assert _needs_web_search("最近的碳价格是多少？") is True
    plan = _plan_agent_tools(
        "最近的碳价格是多少？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is True
    assert plan.use_doc_retrieval is True
    assert "联网" in plan.intent_label


def test_carbon_price_without_web_config():
    plan = _plan_agent_tools(
        "最近的碳价格是多少？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=False,
    )
    assert plan.use_web_search is False
    assert plan.use_doc_retrieval is True


def test_explicit_web_search_request():
    assert _needs_web_search("帮我上网查一下欧盟碳价") is True
    plan = _plan_agent_tools(
        "帮我上网查一下欧盟碳价",
        attach_count=0,
        kb_enabled=False,
        kg_enabled=False,
        web_enabled=True,
    )
    assert plan.use_web_search is True
    assert plan.use_doc_retrieval is False
    assert plan.intent_label == "联网检索实时信息"


def test_policy_process_skips_web_search():
    assert _needs_web_search("碳配额发放流程是什么？") is False
    plan = _plan_agent_tools(
        "碳配额发放流程是什么？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert plan.use_web_search is False
