"""引用片段格式化测试。"""

from __future__ import annotations

from app.integrations.citation_snippet import format_citation_snippet


def test_prefers_knowflow_highlight_with_em():
    out = format_citation_snippet(
        highlight="关于<em>体检</em>的通知",
        content="关于示例公司 2026 年度员工体检的通知\n各部门：\n" + ("为保障员工健康。" * 20),
        question="体检时间",
    )
    assert "<em>体检</em>" in out
    assert len(out) < 200


def test_extracts_short_excerpt_when_no_highlight():
    long_body = "前言。" + ("无关内容。" * 40) + "烟台效航健康体检安排说明。" + ("附录。" * 10)
    out = format_citation_snippet(
        highlight="",
        content=long_body,
        question="烟台效航体检",
    )
    assert "烟台" in out
    assert "<em>" in out
    assert len(out) <= 500


def test_highlight_shorter_than_content_used():
    content = "A" * 800
    highlight = "命中<em>关键词</em>片段"
    out = format_citation_snippet(highlight=highlight, content=content, question="关键词")
    assert "<em>关键词</em>" in out
    assert len(out) < 100


def test_highlights_chinese_question_when_knowflow_returns_plain_content():
    long_body = "前言。" + ("无关内容。" * 40) + "烟台效航健康体检安排说明。" + ("附录。" * 10)
    out = format_citation_snippet(
        highlight=long_body,
        content=long_body,
        question="烟台效航体检安排",
    )
    assert "烟台" in out
    assert "<em>" in out
    assert len(out) <= 500
