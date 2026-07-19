"""双碳官方源取数 — 碳价 / 政策 / 排放·CCER·国际·地方数据。

从官方渠道抓取 HTML 并做内存摘要，不持久化原文。新闻资讯不走本服务，
由浏览器工具（invoke_context_subagent kind=execute）查最新。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_SNIPPET = 800
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header"})
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

CARBON_DATA_TOPICS = frozenset({"emission", "ccer", "international", "local"})

# 各查询类型的数据源（第一顺位为主源）
_SOURCES: dict[str, tuple[str, ...]] = {
    "price": (
        "https://www.cets.org.cn",
        "https://www.cneeex.com",
        "https://www.tanpaifang.com/tanjia/",
    ),
    "policy": (
        "https://www.gov.cn/zhengce/",
        "https://www.ndrc.gov.cn/",
        "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/",
        "https://www.miit.gov.cn/",
    ),
    "emission": (
        "https://www.ipe.org.cn",
        "https://www.ccchina.org.cn",
        "https://www.eco.gov.cn/carbon.html",
    ),
    "ccer": (
        "https://www.cneeex.com",
        "https://www.chinacrc.net.cn",
    ),
    "international": (
        "https://carbon-pulse.com",
        "https://www.eex.com",
        "https://climateimpactx.com",
    ),
    "local": (
        "https://ccnt.igdp.cn",
        "https://www.3060.org.cn",
    ),
}

_TYPE_LABELS = {
    "price": "碳价行情",
    "policy": "政策法规",
    "emission": "排放数据",
    "ccer": "CCER 数据",
    "international": "国际碳市场",
    "local": "地方双碳方案",
}

# 新闻资讯推荐浏览器打开的站点（不在本服务抓取）
NEWS_BROWSER_HINT_URLS = (
    "https://www.cenews.com.cn",
    "https://www.tandao.org",
    "https://www.3060.org.cn",
)


class _HtmlAnalyzer(HTMLParser):
    """轻量 HTML 分析（纯 stdlib）。"""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self._body_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_article = False
        self._article_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "title":
            self._in_title = True
        if t in _SKIP_TAGS:
            self._skip_depth += 1
        if t in ("article", "main") or any(
            k.lower() in ("id", "class")
            and v
            and any(kw in v.lower() for kw in ("content", "article", "main", "detail", "news"))
            for k, v in attrs
        ):
            self._in_article = True
            self._article_depth = len(self._tag_stack)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()
        if t == "title":
            self._in_title = False
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._in_article and len(self._tag_stack) < self._article_depth:
            self._in_article = False

    def handle_data(self, data: str) -> None:
        text = _clean(data)
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self._skip_depth == 0:
            tag = self._tag_stack[-1] if self._tag_stack else ""
            if tag in _HEADING_TAGS:
                if text not in self.headings:
                    self.headings.append(text)
            else:
                self._body_parts.append(text)


def _clean(text: str) -> str:
    return unescape(re.sub(r"\s+", " ", (text or ""))).strip()


def _extract_price_data(text: str) -> list[str]:
    lines: list[str] = []
    price_kw = (
        "碳价", "成交价", "均价", "收盘价", "开盘价", "最高价", "最低价",
        "成交量", "成交额", "交易量", "交易额", "挂牌", "大宗",
        "CEA", "CCER", "配额", "碳配额", "元/吨",
    )
    for line in text.split("。"):
        line = line.strip()
        if not line:
            continue
        if any(kw in line for kw in price_kw):
            numbers = re.findall(r"[\d,]+\.?\d*", line)
            if numbers:
                lines.append(line[:200])
    return lines


def _extract_policy_data(text: str) -> list[str]:
    lines: list[str] = []
    policy_kw = (
        "印发", "发布", "通知", "意见", "方案", "规划",
        "碳达峰", "碳中和", "节能减排", "绿色", "低碳", "双碳",
        "实施", "试行", "暂行", "办法", "规定", "条例",
    )
    for para in text.split("。"):
        para = para.strip()
        if not para:
            continue
        if any(kw in para for kw in policy_kw):
            lines.append(para[:200])
    return lines


def analyze_html(html: str, query_type: str = "") -> dict[str, Any]:
    parser = _HtmlAnalyzer()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    title = _clean(parser.title) or "（无 title）"
    full_text = " ".join(parser._body_parts)

    extracted: list[str] = []
    if query_type == "price":
        extracted = _extract_price_data(full_text)
    elif query_type == "policy":
        extracted = _extract_policy_data(full_text)

    if extracted:
        snippet = "；".join(extracted[:_MAX_SNIPPET])[:3000]
    else:
        snippet = full_text[:_MAX_SNIPPET] or "（无摘要）"

    return {
        "title": title,
        "headings": parser.headings[:10],
        "snippet": snippet,
        "extracted": extracted[:20],
    }


def build_source_block(url: str, data: dict[str, Any], query_type: str = "") -> str:
    headings = data.get("headings") or []
    heading_text = "、".join(headings[:5]) if headings else "（无明显标题）"
    extracted = data.get("extracted") or []
    extracted_text = ""
    if extracted:
        extracted_text = "\n关键数据：\n" + "\n".join(
            f"  - {item[:200]}" for item in extracted[:10]
        )
    snippet = str(data.get("snippet") or "")[:600]
    type_label = _TYPE_LABELS.get(query_type, "双碳资讯")
    return (
        f"【{type_label}】\n"
        f"URL：{url}\n"
        f"标题：{data.get('title')}\n"
        f"主要标题：{heading_text}\n"
        f"正文摘要：{snippet}"
        f"{extracted_text}"
    )


def _filter_by_keyword(block: str, keyword: str) -> bool:
    kw = (keyword or "").strip()
    if not kw:
        return True
    return kw.lower() in block.lower()


async def _fetch_html(url: str, *, timeout: float = 12.0) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=False,
            follow_redirects=True,
            headers={"User-Agent": _DEFAULT_UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.debug("carbon fetch failed url=%s err=%s", url, exc)
        return None


async def _fetch_sources(
    query_type: str,
    *,
    keyword: str = "",
    url: str = "",
) -> dict[str, Any]:
    """从官方源抓取并汇总摘要。"""
    queried_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    sources_out: list[dict[str, Any]] = []
    blocks: list[str] = []
    failed: list[str] = []

    if url.startswith(("http://", "https://")):
        target_urls: tuple[str, ...] = (url,)
    else:
        target_urls = _SOURCES.get(query_type, ())

    if not target_urls:
        return {
            "ok": False,
            "query_type": query_type,
            "keyword": keyword,
            "queried_at": queried_at,
            "sources": [],
            "failed_urls": [],
            "summary_md": f"未知查询类型：{query_type}",
            "error": "unknown_query_type",
        }

    for src in target_urls:
        html = await _fetch_html(src)
        if not html:
            failed.append(src)
            continue
        data = analyze_html(html, query_type=query_type)
        block = build_source_block(src, data, query_type=query_type)
        if keyword and not _filter_by_keyword(block, keyword):
            # 关键词未命中时仍保留源摘要（官网首页常无关键词），但标注
            block = block + f"\n（关键词「{keyword}」未在摘要中直接命中，以上为该源首页摘要）"
        sources_out.append({
            "url": src,
            "title": data.get("title"),
            "headings": data.get("headings"),
            "snippet": data.get("snippet"),
            "extracted": data.get("extracted"),
        })
        blocks.append(block)

    if not blocks:
        tried = ", ".join(target_urls)
        summary = (
            f"所有数据源均暂时无法访问，无法获取 [{query_type}] 数据。\n"
            f"尝试获取的来源：{tried}\n"
            f"请稍后重试；新闻资讯类请用浏览器工具查最新。"
        )
        return {
            "ok": False,
            "query_type": query_type,
            "keyword": keyword,
            "queried_at": queried_at,
            "sources": [],
            "failed_urls": failed,
            "summary_md": summary,
            "error": "all_sources_failed",
        }

    summary_md = "\n\n---\n\n".join(blocks)
    if failed:
        summary_md += f"\n\n（以下来源暂时无法访问，已跳过：{', '.join(failed)}）"
    if keyword:
        summary_md = f"查询关键词：{keyword}\n查询时间：{queried_at}\n\n{summary_md}"
    else:
        summary_md = f"查询时间：{queried_at}\n\n{summary_md}"

    return {
        "ok": True,
        "query_type": query_type,
        "keyword": keyword,
        "queried_at": queried_at,
        "sources": sources_out,
        "failed_urls": failed,
        "summary_md": summary_md,
        "error": None,
    }


async def fetch_carbon_price(*, keyword: str = "", url: str = "") -> dict[str, Any]:
    """获取 CEA/CCER/试点等碳价行情摘要。"""
    return await _fetch_sources("price", keyword=keyword, url=url)


async def fetch_carbon_policy(*, keyword: str = "", url: str = "") -> dict[str, Any]:
    """获取双碳政策法规摘要（gov/ndrc/mee/miit 等）。"""
    return await _fetch_sources("policy", keyword=keyword, url=url)


async def fetch_carbon_data(
    topic: str,
    *,
    keyword: str = "",
    url: str = "",
) -> dict[str, Any]:
    """获取排放 / CCER / 国际碳市场 / 地方双碳方案数据。"""
    t = (topic or "").strip().lower()
    if t not in CARBON_DATA_TOPICS:
        queried_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return {
            "ok": False,
            "query_type": t,
            "keyword": keyword,
            "queried_at": queried_at,
            "sources": [],
            "failed_urls": [],
            "summary_md": (
                f"无效 topic：{topic}。可选：emission / ccer / international / local。"
            ),
            "error": "invalid_topic",
        }
    return await _fetch_sources(t, keyword=keyword, url=url)


def news_browser_task_hint(question: str = "") -> str:
    """新闻/资讯类问题的浏览器执行任务提示。"""
    q = (question or "").strip() or "最新双碳新闻资讯"
    urls = "、".join(NEWS_BROWSER_HINT_URLS)
    return (
        f"用浏览器打开碳资讯站点（{urls}）查询并摘要：{q}。"
        "优先打开列表页最新条目，必要时进入详情页核对发布时间与来源。"
    )
