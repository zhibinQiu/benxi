"""报告生成 Agent 辅助逻辑测试。"""

from __future__ import annotations

from app.schemas.ai_chat import AiChatMessage
from app.services.report_generation_service import (
    _SOURCE_PRIORITY_RULE,
    _build_messages,
    _has_prior_assistant_turn,
    build_aligned_report_sources,
    build_local_retrieval_queries,
    build_report_context_block,
    build_search_queries,
    build_web_citations,
    classify_intent,
    extract_report_topic,
    finalize_report_citations,
    merge_retrieval_hits,
    resolve_report_topic,
)


def test_extract_report_topic_from_generate_phrase():
    topic = extract_report_topic("请生成一份关于全国碳市场的研究报告")
    assert "全国碳市场" in topic


def test_classify_intent_format_adjust():
    assert classify_intent("请把报告改成表格形式", has_history=True) == "format_adjust"


def test_classify_intent_short_format_with_history_context():
    history = [
        AiChatMessage(role="user", content="请生成全国碳市场研究报告"),
        AiChatMessage(role="assistant", content="## 摘要\n全国碳市场…"),
    ]
    assert classify_intent("表格", has_history=True, history=history) == "format_adjust"


def test_classify_intent_short_follow_up_with_history_context():
    history = [
        AiChatMessage(role="user", content="请生成全国碳市场研究报告"),
        AiChatMessage(role="assistant", content="## 摘要\n全国碳市场…"),
    ]
    assert classify_intent("海外案例", has_history=True, history=history) == "follow_up"


def test_resolve_report_topic_from_first_user_message():
    history = [
        AiChatMessage(role="user", content="请生成一份关于全国碳市场的研究报告"),
        AiChatMessage(role="assistant", content="## 摘要\n…"),
    ]
    topic = resolve_report_topic("补充海外案例", history)
    assert "全国碳市场" in topic


def test_build_local_retrieval_queries_follow_up_uses_topic():
    history = [
        AiChatMessage(role="user", content="请生成全国碳市场研究报告"),
        AiChatMessage(role="assistant", content="## 背景\n…"),
    ]
    queries = build_local_retrieval_queries(
        "海外案例",
        topic="全国碳市场",
        intent="follow_up",
        history=history,
    )
    assert queries[0] == "全国碳市场"
    assert any("海外案例" in q for q in queries)


def test_classify_intent_expand_is_follow_up_not_format():
    assert classify_intent("请扩写第三章，补充更多案例", has_history=True) == "follow_up"


def test_classify_intent_follow_up():
    assert classify_intent("补充一下海外案例", has_history=True) == "follow_up"


def test_classify_intent_initial():
    assert classify_intent("生成 AI 质检应用调研报告", has_history=False) == "initial"


def test_has_prior_assistant_turn_requires_assistant_content():
    from app.schemas.ai_chat import AiChatMessage

    assert not _has_prior_assistant_turn(
        [AiChatMessage(role="user", content="生成报告")]
    )
    assert _has_prior_assistant_turn(
        [
            AiChatMessage(role="user", content="生成报告"),
            AiChatMessage(role="assistant", content="## 摘要\n正文"),
        ]
    )


def test_build_search_queries_dedup():
    queries = build_search_queries(
        "补充碳市场细节",
        topic="全国碳市场",
        intent="follow_up",
    )
    assert queries[0] == "全国碳市场"
    assert len(queries) >= 1


def test_build_web_citations_index_offset():
    items = [
        {"title": "A", "url": "https://a.test", "snippet": "sa"},
        {"title": "B", "url": "https://b.test", "snippet": "sb"},
    ]
    cites = build_web_citations(items, start_index=3)
    assert cites[0]["index"] == 3
    assert cites[1]["index"] == 4
    assert cites[0]["source"] == "web"


def test_build_local_retrieval_queries_multi_aspect():
    queries = build_local_retrieval_queries(
        "生成碳市场报告",
        topic="全国碳市场",
        intent="initial",
    )
    assert queries[0] == "全国碳市场"
    assert len(queries) >= 4
    assert any("背景" in q for q in queries)


def test_merge_retrieval_hits_dedup_by_chunk():
    hits = [
        {"chunk_id": "a", "score": 0.9, "content": "one"},
        {"chunk_id": "a", "score": 0.5, "content": "one"},
        {"chunk_id": "b", "score": 0.8, "content": "two"},
    ]
    merged = merge_retrieval_hits(hits, max_total=10)
    assert len(merged) == 2
    assert merged[0]["chunk_id"] == "a"


def test_build_report_context_block_keeps_long_body():
    hits = [
        {
            "document_id": "d1",
            "content": "长文" * 500,
            "anchor_json": {"page": 3},
        }
    ]
    block = build_report_context_block(hits, {"d1": "测试文档"}, max_total_chars=5000)
    assert block.startswith("[1]")
    assert "长文" in block
    assert "测试文档" not in block
    assert len(block) > 200


def test_aligned_sources_skip_empty_body_and_reindex():
    hits = [
        {"document_id": "d1", "content": "第一段", "score": 0.9},
        {"document_id": "d2", "content": "", "score": 0.8},
        {"document_id": "d3", "content": "第三段", "score": 0.7},
    ]
    local_ctx, _, cites, count = build_aligned_report_sources(
        hits,
        {"d1": "A", "d2": "B", "d3": "C"},
        [],
    )
    assert count == 2
    assert "[1]" in local_ctx and "第一段" in local_ctx
    assert "[2]" in local_ctx and "第三段" in local_ctx
    assert "[3]" not in local_ctx
    assert len(cites) == 2
    assert cites[0]["index"] == 1
    assert cites[1]["index"] == 2
    assert cites[1]["title"] == "C"


def test_finalize_report_preserves_citation_index():
    citations = [
        {"index": 1, "document_id": "a", "title": "Doc A", "snippet": "alpha"},
        {"index": 2, "document_id": "b", "title": "Doc B", "snippet": "beta"},
    ]
    answer = "结论一 [1]。另一事实 [2]。"
    normalized, kept = finalize_report_citations(answer, citations)
    assert "[1]" in normalized and "[2]" in normalized
    assert len(kept) == 2
    assert kept[1]["index"] == 2


def test_strip_report_reference_section():
    raw = "## 结论\n内容 [1]。\n\n## 参考来源\n- 文档A"
    answer, kept = finalize_report_citations(
        raw,
        [{"index": 1, "document_id": "a", "title": "A", "snippet": "x"}],
    )
    assert "参考来源" not in answer
    assert "结论" in answer


def test_build_messages_includes_source_priority():
    messages = _build_messages(
        message="生成碳市场报告",
        history=[],
        intent="initial",
        topic="全国碳市场",
        local_context="[1]\n本地片段",
        web_context="[2]\n联网片段",
        web_enabled=True,
        local_enabled=True,
        chunk_count=1,
    )
    system = messages[0]["content"]
    assert _SOURCE_PRIORITY_RULE in system
    assert "优先级 1" in system and "本地知识库" in system
    assert "优先级 2" in system and "联网检索" in system
    assert "本地片段" in system and "联网片段" in system


def test_generate_report_mindmap_local_fallback():
    from app.services.report_generation_service import generate_report_mindmap

    mermaid, source = generate_report_mindmap(
        question="碳市场",
        answer="## 背景\n- 全国碳市场启动\n## 结论\n- 逐步扩围",
    )
    assert mermaid
    assert "mindmap" in mermaid.lower()
    assert source in {"llm", "local"}
