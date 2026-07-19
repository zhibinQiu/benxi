"""carbon_service 解析与工具注册单测（不依赖外网）。"""

from __future__ import annotations

import asyncio

from app.core.agent_tool_args import TOOL_DEFINITIONS
from app.core.tool_skill_taxonomy import AGENT_TOOL_WHITELIST, DEFAULT_AGENT_TOOLS
from app.services import carbon_service as svc
from app.skills.registry import get_skill


SAMPLE_PRICE_HTML = """
<html><head><title>全国碳市场行情</title></head>
<body>
<main>
<h1>CEA 今日行情</h1>
<p>今日全国碳市场挂牌协议交易成交价为 85.20 元/吨，成交量 12000 吨。</p>
<p>大宗交易均价 84.50 元/吨。</p>
</main>
</body></html>
"""

SAMPLE_POLICY_HTML = """
<html><head><title>政策发布</title></head>
<body>
<article>
<h2>关于印发碳达峰实施方案的通知</h2>
<p>生态环境部发布碳达峰碳中和相关意见，要求各地落实节能减排办法。</p>
</article>
</body></html>
"""


def test_analyze_html_price_extracts_numbers():
    data = svc.analyze_html(SAMPLE_PRICE_HTML, query_type="price")
    assert "碳市场" in str(data["title"]) or "行情" in str(data["title"])
    assert data["extracted"]
    joined = " ".join(data["extracted"])
    assert "85.20" in joined or "元/吨" in joined


def test_analyze_html_policy_extracts_paragraphs():
    data = svc.analyze_html(SAMPLE_POLICY_HTML, query_type="policy")
    assert data["extracted"]
    joined = " ".join(data["extracted"])
    assert "碳达峰" in joined or "印发" in joined


def test_build_source_block_contains_url():
    data = svc.analyze_html(SAMPLE_PRICE_HTML, query_type="price")
    block = svc.build_source_block("https://www.cets.org.cn", data, query_type="price")
    assert "https://www.cets.org.cn" in block
    assert "碳价行情" in block


def test_invalid_carbon_data_topic():
    result = asyncio.run(svc.fetch_carbon_data("not-a-topic"))
    assert result["ok"] is False
    assert result["error"] == "invalid_topic"


def test_all_sources_failed_when_fetch_returns_none(monkeypatch):
    async def _none(_url: str, *, timeout: float = 12.0):
        return None

    monkeypatch.setattr(svc, "_fetch_html", _none)
    result = asyncio.run(svc.fetch_carbon_price())
    assert result["ok"] is False
    assert result["error"] == "all_sources_failed"
    assert "无法访问" in result["summary_md"]


def test_fetch_carbon_price_success_mocked(monkeypatch):
    async def _html(url: str, *, timeout: float = 12.0):
        return SAMPLE_PRICE_HTML

    monkeypatch.setattr(svc, "_fetch_html", _html)
    result = asyncio.run(svc.fetch_carbon_price(keyword="CEA"))
    assert result["ok"] is True
    assert result["sources"]
    assert "查询时间" in result["summary_md"]


def test_news_browser_task_hint():
    hint = svc.news_browser_task_hint("今日碳新闻")
    assert "cenews.com.cn" in hint
    assert "今日碳新闻" in hint
    assert "浏览器" in hint


def test_carbon_tools_registered_in_definitions():
    for name in ("carbon_price", "carbon_policy", "carbon_data"):
        assert name in TOOL_DEFINITIONS


def test_carbon_agent_whitelist_includes_carbon_tools():
    atomic = AGENT_TOOL_WHITELIST["carbon"]["atomic"]
    for name in ("carbon_price", "carbon_policy", "carbon_data"):
        assert name in atomic
    tools = DEFAULT_AGENT_TOOLS["carbon"]
    for name in ("carbon_price", "carbon_policy", "carbon_data"):
        assert name in tools


def test_carbon_qa_skill_registered():
    from app.skills.registry import ensure_skills_loaded

    ensure_skills_loaded()
    skill = get_skill("carbon-qa")
    assert skill is not None
    assert skill.name == "carbon-qa"
    action_names = {t.name for t in skill.tools}
    assert "ask" in action_names


def test_classify_carbon_question():
    from app.skills.builtin.handlers import _classify_carbon_question

    assert _classify_carbon_question("今天全国碳市场成交价多少") == "price"
    assert _classify_carbon_question("最新双碳政策有哪些") == "policy"
    assert _classify_carbon_question("今日碳新闻资讯") == "news"
    assert _classify_carbon_question("CCER 方法学进展") == "ccer"
    assert _classify_carbon_question("什么是碳达峰") == "general"
