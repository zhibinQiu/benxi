"""默认检索优先级。"""

from __future__ import annotations

from app.services.retrieval_priority import (
    DEFAULT_RETRIEVAL_TOOL_ORDER,
    parse_explicit_retrieval_channels,
    resolve_retrieval_channel_plan,
)


def test_default_tool_order():
    assert DEFAULT_RETRIEVAL_TOOL_ORDER == (
        "kg_query",
        "web_search",
        "knowledge_retrieve",
    )


def test_explicit_kb_only():
    plan = resolve_retrieval_channel_plan(
        "帮我检索知识库里的碳排放报告",
        kb_allowed=True,
        kg_allowed=True,
        web_allowed=True,
    )
    assert plan.explicit is True
    assert plan.run_kb is True
    assert plan.run_kg is False
    assert plan.run_web is False


def test_explicit_web_overrides_default():
    channels = parse_explicit_retrieval_channels("请联网搜索最新政策")
    assert channels is not None
    assert channels["web"] is True


def test_implicit_enables_cascade_channels():
    plan = resolve_retrieval_channel_plan(
        "帮我查一下资料",
        kb_allowed=True,
        kg_allowed=True,
        web_allowed=True,
    )
    assert plan.explicit is False
    assert plan.run_kg and plan.run_web and plan.run_kb
