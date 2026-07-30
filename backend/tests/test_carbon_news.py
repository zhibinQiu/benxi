"""碳新闻 crawl / ask 单测（mock 爬虫与 LLM）。"""

from __future__ import annotations

import asyncio

from app.schemas.carbon_news import CarbonNewsItem
from app.services import carbon_news_service as svc


def test_crawl_carbon_news_maps_scraper_rows(monkeypatch):
    async def _fake_scrape(self, **_kwargs):
        self.total_hits = 3
        return [
            {
                "title": "碳达峰方案",
                "url": "https://www.ndrc.gov.cn/a.html",
                "doc_type": "政务公开",
                "published_at": "2026-01-01",
                "source": "发改委",
                "body": "第一段。\n\n第二段。",
            },
            {
                "title": "",
                "url": "",
                "doc_type": "",
                "published_at": "",
                "source": "",
                "body": "",
            },
        ]

    async def _noop_close(self):
        return None

    monkeypatch.setattr(svc.NdrcPolicySearcher, "scrape", _fake_scrape)
    monkeypatch.setattr(svc.NdrcPolicySearcher, "aclose", _noop_close)

    out = asyncio.run(svc.crawl_carbon_news(keyword="碳达峰", limit=100))
    assert out.keyword == "碳达峰"
    assert out.total_hits == 3
    assert out.count == 1
    assert out.items[0].title == "碳达峰方案"
    assert out.items[0].doc_type == "政务公开"
    assert "第二段" in out.items[0].body


def test_ask_carbon_news_uses_llm_and_sources(monkeypatch):
    items = [
        CarbonNewsItem(
            title="条例发布",
            url="https://www.ndrc.gov.cn/x.html",
            doc_type="新闻动态",
            published_at="2026-02-01",
            source="发改委",
            body="全国碳市场扩围相关要求。",
        )
    ]

    async def _fake_llm(**_kwargs):
        return {
            "message": {
                "content": "根据证据，全国碳市场扩围有新要求。[1]\n\n## 数据来源\n\n1. 条例发布"
            }
        }

    monkeypatch.setattr(svc, "is_configured", lambda: True)
    monkeypatch.setattr(svc, "chat_completion_message_async", _fake_llm)

    out = asyncio.run(svc.ask_carbon_news(question="碳市场有什么新规？", items=items))
    assert "全国碳市场" in out.answer_md
    assert len(out.sources) == 1
    assert out.sources[0].url == "https://www.ndrc.gov.cn/x.html"
    assert out.sources[0].doc_type == "新闻动态"


def test_ask_carbon_news_empty_items():
    out = asyncio.run(svc.ask_carbon_news(question="有哪些政策？", items=[]))
    assert "先" in out.answer_md or "爬取" in out.answer_md
    assert out.sources == []


def test_ask_carbon_news_appends_sources_when_missing(monkeypatch):
    items = [
        CarbonNewsItem(
            title="政策A",
            url="https://example.com/a",
            body="正文A" * 20,
        )
    ]

    async def _fake_llm(**_kwargs):
        return {"message": {"content": "这是仅有总结、未列来源的回答。"}}

    monkeypatch.setattr(svc, "is_configured", lambda: True)
    monkeypatch.setattr(svc, "chat_completion_message_async", _fake_llm)

    out = asyncio.run(svc.ask_carbon_news(question="总结一下", items=items))
    assert "数据来源" in out.answer_md
    assert "政策A" in out.answer_md
    assert out.sources[0].title == "政策A"
