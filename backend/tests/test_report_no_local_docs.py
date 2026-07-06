"""报告生成：未选本地文档时知识库检索规划仍应合理。"""

from __future__ import annotations

from app.services.knowledge_agentic_service import (
    _evaluate_report_sufficiency,
    _plan_report_gathering_fallback,
)


def test_plan_report_gathering_fallback_no_sources():
    local, web, reasoning = _plan_report_gathering_fallback(
        message="请生成全国碳市场研究报告",
        topic="全国碳市场",
        intent="initial",
        local_allowed=False,
        web_allowed=False,
        history_excerpt="",
    )
    assert local == []
    assert web == []
    assert "模型知识" in reasoning


def test_plan_report_gathering_fallback_format_adjust_skips_retrieval():
    local, web, reasoning = _plan_report_gathering_fallback(
        message="请改成表格形式",
        topic="全国碳市场",
        intent="format_adjust",
        local_allowed=True,
        web_allowed=True,
        history_excerpt="用户：生成报告\n助手：## 摘要\n正文",
    )
    assert local == []
    assert web == []
    assert "格式调整" in reasoning


def test_evaluate_report_sufficiency_skips_when_no_retrieval_attempted():
    sufficient, gaps, extra_local, extra_web = _evaluate_report_sufficiency(
        topic="全国碳市场",
        message="请把报告改成表格形式",
        local_count=0,
        web_count=0,
        snippet_preview="",
        local_docs_available=True,
        web_allowed=True,
        intent="format_adjust",
        retrieval_attempted=False,
        history_available=True,
    )
    assert sufficient is True
    assert gaps is None
    assert extra_local == []
    assert extra_web == []


def test_evaluate_report_sufficiency_no_docs_no_web_allows_model_knowledge():
    sufficient, gaps, extra_local, extra_web = _evaluate_report_sufficiency(
        topic="全国碳市场",
        message="请生成研究报告",
        local_count=0,
        web_count=0,
        snippet_preview="",
        local_docs_available=False,
        web_allowed=False,
    )
    assert sufficient is True
    assert gaps is None
    assert extra_local == []
    assert extra_web == []
