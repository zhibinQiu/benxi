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
    async def _none(_client, _url: str):
        return None

    monkeypatch.setattr(svc, "_fetch_html", _none)
    result = asyncio.run(svc.fetch_carbon_price())
    assert result["ok"] is False
    assert result["error"] == "all_sources_failed"
    assert "无法访问" in result["summary_md"]


def test_fetch_carbon_price_success_mocked(monkeypatch):
    async def _html(_client, url: str):
        return SAMPLE_PRICE_HTML

    monkeypatch.setattr(svc, "_fetch_html", _html)
    result = asyncio.run(svc.fetch_carbon_price(keyword="CEA"))
    assert result["ok"] is True
    assert result["sources"]
    assert "查询时间" in result["summary_md"]


def test_fetch_sources_runs_in_parallel(monkeypatch):
    """多源串行挂起会拖垮看板；并行后最坏约等于单源 timeout。"""
    import time

    calls: list[str] = []

    async def _slow(_client, url: str):
        calls.append(url)
        await asyncio.sleep(0.25)
        return SAMPLE_PRICE_HTML

    monkeypatch.setattr(svc, "_fetch_html", _slow)
    started = time.monotonic()
    result = asyncio.run(svc.fetch_carbon_price(timeout=2.0))
    elapsed = time.monotonic() - started
    assert result["ok"] is True
    assert len(calls) == len(svc._SOURCES["price"])
    # 串行约 0.75s+；并行应明显低于串行下界
    assert elapsed < 0.6


def test_news_browser_task_hint():
    hint = svc.news_browser_task_hint("今日碳新闻")
    assert "cenews.com.cn" in hint
    assert "今日碳新闻" in hint
    assert "浏览器" in hint


def test_carbon_tools_registered_in_definitions():
    for name in ("carbon_price", "carbon_policy", "carbon_data", "time_series_forecast"):
        assert name in TOOL_DEFINITIONS


def test_carbon_agent_whitelist_includes_carbon_tools():
    atomic = AGENT_TOOL_WHITELIST["carbon"]["atomic"]
    for name in ("carbon_price", "carbon_policy", "carbon_data", "time_series_forecast"):
        assert name in atomic
    tools = DEFAULT_AGENT_TOOLS["carbon"]
    for name in ("carbon_price", "carbon_policy", "carbon_data", "time_series_forecast"):
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
    assert _classify_carbon_question("CEA 至年底价格预测") == "forecast"
    assert _classify_carbon_question("用 prophet 外推碳价") == "forecast"
    assert _classify_carbon_question("最新双碳政策有哪些") == "policy"
    assert _classify_carbon_question("今日碳新闻资讯") == "news"
    assert _classify_carbon_question("CCER 方法学进展") == "ccer"
    assert _classify_carbon_question("什么是碳达峰") == "general"


def test_carbon_policy_writes_citations_to_loop_state(monkeypatch):
    """carbon_policy 成功后须写入 loop_state.citations，供前端「数据来源」展示。"""
    from app.tool_center.adapters import _run_carbon_policy
    from app.tool_center.context import ToolRuntimeContext

    fake = {
        "ok": True,
        "summary_md": "政策摘要正文",
        "sources": [
            {
                "url": "https://www.gov.cn/zhengce/",
                "title": "政策_中国政府网",
                "snippet": "最新政策列表",
                "extracted": ["碳达峰"],
            },
            {
                "url": "https://www.ndrc.gov.cn/",
                "title": "国家发改委",
                "snippet": "发改要闻",
                "extracted": [],
            },
        ],
        "failed_urls": [],
        "queried_at": "t",
        "query_type": "policy",
        "keyword": "双碳",
        "error": None,
    }

    async def _fake(**_kwargs):
        return fake

    monkeypatch.setattr(svc, "fetch_carbon_policy", _fake)
    loop_state: dict = {"citations": [], "retrieval_context_parts": []}
    ctx = ToolRuntimeContext(
        db=None,  # type: ignore[arg-type]
        user=None,  # type: ignore[arg-type]
        loop_state=loop_state,
    )
    ok, summary, data = asyncio.run(_run_carbon_policy(ctx, {"keyword": "双碳"}))
    assert ok is True
    assert "2 个政策" in summary
    assert data and data["ok"] is True
    cites = loop_state["citations"]
    assert len(cites) == 2
    assert cites[0]["index"] == 1
    assert cites[0]["url"] == "https://www.gov.cn/zhengce/"
    assert cites[0]["title"] == "政策_中国政府网"
    assert cites[0]["source"] == "web"
    assert cites[1]["url"] == "https://www.ndrc.gov.cn/"
    retrieval = "\n".join(loop_state["retrieval_context_parts"])
    assert "数据来源" in retrieval
    assert "https://www.gov.cn/zhengce/" in retrieval
