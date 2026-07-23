"""资讯 BM25 检索单测。"""

from __future__ import annotations

from app.services.subscription_bm25 import (
    ILIKE_FLOOR_SCORE,
    rank_subscription_items,
    strip_html,
    substring_match,
    tokenize,
)


def test_strip_html_and_tokenize():
    assert "碳" in strip_html("<p>碳排放</p>") or "排放" in strip_html("<p>碳排放</p>")
    tokens = tokenize("碳排放权交易市场")
    assert tokens
    assert all(isinstance(t, str) and t for t in tokens)


def test_substring_match_casefold():
    item = {
        "title": "CEA Price Update",
        "summary": "",
        "content_html": "<p>Hello</p>",
    }
    assert substring_match("cea", item)
    assert substring_match("PRICE", item)
    assert not substring_match("无关词", item)


def test_title_match_ranks_above_summary_only():
    items = [
        {
            "ref": "a",
            "title": "今日天气晴朗",
            "summary": "无关摘要",
            "content_html": "",
        },
        {
            "ref": "b",
            "title": "市场周报",
            "summary": "全国碳排放权交易市场运行平稳",
            "content_html": "",
        },
        {
            "ref": "c",
            "title": "碳排放权交易市场最新政策解读",
            "summary": "政策要点",
            "content_html": "",
        },
    ]
    ranked = rank_subscription_items(
        "碳排放权交易市场",
        items,
        ilike_refs=set(),
    )
    assert ranked
    assert ranked[0]["ref"] == "c"
    assert float(ranked[0]["_bm25_score"]) > float(ranked[1]["_bm25_score"])


def test_ilike_floor_keeps_substring_only_hit():
    items = [
        {
            "ref": "x",
            "title": "XYZCorpQ1",
            "summary": "季度财报",
            "content_html": "",
        },
        {
            "ref": "y",
            "title": "其他新闻",
            "summary": "无关",
            "content_html": "",
        },
    ]
    # 连续专有串可能分词后 BM25=0，但仍应被 ILIKE 保底召回
    ranked = rank_subscription_items(
        "XYZCorpQ1",
        items,
        ilike_refs={"x"},
    )
    refs = [r["ref"] for r in ranked]
    assert "x" in refs
    hit = next(r for r in ranked if r["ref"] == "x")
    assert float(hit["_bm25_score"]) >= ILIKE_FLOOR_SCORE


def test_empty_keyword_returns_empty():
    assert rank_subscription_items("", [{"ref": "a", "title": "t"}]) == []
    assert rank_subscription_items("kw", []) == []
