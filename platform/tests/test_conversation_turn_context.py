"""多轮对话上下文辅助。"""

from __future__ import annotations

from app.schemas.ai_chat import AiChatMessage
from app.core.conversation_turn_context import (
    build_turn_planning_context,
    effective_question_for_retrieval,
    follow_up_thinking_hint,
    is_likely_follow_up,
    plan_cache_applicable,
)
from app.services.agent_intent import needs_knowledge_retrieval, needs_web_search


def _history() -> list[AiChatMessage]:
    return [
        AiChatMessage(role="user", content="最近的碳价格是多少？"),
        AiChatMessage(
            role="assistant",
            content="全国碳市场近期收盘价约在 90 元/吨左右……",
        ),
    ]


def test_is_likely_follow_up_short_region_question():
    assert is_likely_follow_up("广东呢？", _history()) is True


def test_is_likely_follow_up_continue_phrase():
    assert is_likely_follow_up("继续详细说说", _history()) is True


def test_is_likely_follow_up_thanks_is_not_follow_up():
    assert is_likely_follow_up("谢谢", _history()) is False


def test_effective_question_for_retrieval_merges_anchor():
    text = effective_question_for_retrieval("广东呢？", _history())
    assert "碳价格" in text
    assert "广东" in text


def test_build_turn_planning_context_includes_prior_turns():
    ctx = build_turn_planning_context("广东呢？", _history())
    assert "当前输入" in ctx
    assert "碳价格" in ctx
    assert "近期对话" in ctx


def test_plan_cache_not_applicable_for_follow_up():
    assert plan_cache_applicable("广东呢？", _history()) is False
    assert plan_cache_applicable("最近的碳价格是多少？", None) is True


def test_follow_up_thinking_hint():
    hint = follow_up_thinking_hint("广东呢？", _history())
    assert "碳价格" in hint


def test_needs_web_search_for_short_follow_up():
    assert needs_web_search("广东呢？", _history()) is True


def test_needs_knowledge_retrieval_for_follow_up_after_business():
    history = [
        AiChatMessage(role="user", content="碳配额发放流程是什么？"),
        AiChatMessage(role="assistant", content="根据检索材料……"),
    ]
    assert needs_knowledge_retrieval("那第二步呢？", history) is True
