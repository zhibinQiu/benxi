"""双碳官方源取数 — 碳价 / 政策 / 排放·CCER·国际·地方数据。

从官方渠道抓取 HTML 并做内存摘要，不持久化原文。新闻资讯不走本服务，
由浏览器工具（invoke_context_subagent kind=execute）查最新。
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_SNIPPET = 800
_DEFAULT_FETCH_TIMEOUT = 8.0
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
        "https://www.ccn.ac.cn/cets",
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
    # 站外新闻/行业媒体（政策检索时一并拉取，不局限于官网）
    "policy_news": (
        "https://www.cenews.com.cn",
        "https://www.tandao.org",
        "https://www.3060.org.cn",
        "https://www.tanpaifang.com/",
        "https://carbon-pulse.com",
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
    "policy_news": "碳市场新闻",
    "emission": "排放数据",
    "ccer": "CCER 数据",
    "international": "国际碳市场",
    "local": "地方双碳方案",
}

# 与全国碳市场/履约相关的主题词（用于过滤无关首页摘要）
_CARBON_TOPIC_KW = (
    "碳市场",
    "碳排放",
    "碳交易",
    "碳排放权",
    "CEA",
    "CCER",
    "履约",
    "配额",
    "双碳",
    "碳达峰",
    "碳中和",
    "控排",
    "温室气体",
    "自愿减排",
    "全国碳",
    "清缴",
    "碳价",
)

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
    text = (block or "").lower()
    tokens = [t for t in re.split(r"\s+", kw.lower()) if len(t) >= 2]
    if not tokens:
        return kw.lower() in text
    # 任一词命中即可（避免整句关键词过严导致全丢）
    return any(t in text for t in tokens)


def _is_carbon_topic_relevant(block: str) -> bool:
    text = (block or "").lower()
    return any(k.lower() in text for k in _CARBON_TOPIC_KW)


def _source_is_relevant(
    *,
    query_type: str,
    keyword: str,
    block: str,
    extracted: list[str] | None,
) -> bool:
    """官网/新闻：无相关内容则丢弃，避免塞进无关首页摘要。"""
    if query_type not in ("policy", "policy_news"):
        if keyword and not _filter_by_keyword(block, keyword):
            # 非政策类仍保留源（兼容旧行为），但政策类严格过滤
            return True
        return True
    # 政策/新闻：必须与碳市场主题相关，或命中查询关键词且抽到有效句
    topic_ok = _is_carbon_topic_relevant(block) or bool(extracted)
    if not topic_ok:
        return False
    if keyword and not (
        _filter_by_keyword(block, keyword) or _is_carbon_topic_relevant(block)
    ):
        return False
    return True


async def _fetch_html(
    client: httpx.AsyncClient,
    url: str,
) -> str | None:
    try:
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
    timeout: float = _DEFAULT_FETCH_TIMEOUT,
) -> dict[str, Any]:
    """从官方源并行抓取并汇总摘要。"""
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

    http_timeout = httpx.Timeout(timeout, connect=min(3.0, timeout))
    async with httpx.AsyncClient(
        timeout=http_timeout,
        verify=False,
        follow_redirects=True,
        headers={"User-Agent": _DEFAULT_UA},
    ) as client:
        pages = await asyncio.gather(*[_fetch_html(client, src) for src in target_urls])

    for src, html in zip(target_urls, pages):
        if not html:
            failed.append(src)
            continue
        data = analyze_html(html, query_type=query_type)
        block = build_source_block(src, data, query_type=query_type)
        extracted = data.get("extracted") or []
        if not _source_is_relevant(
            query_type=query_type,
            keyword=keyword,
            block=block,
            extracted=extracted if isinstance(extracted, list) else [],
        ):
            # 无相关内容：跳过，不把官网无关首页塞进报告
            continue
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


async def fetch_carbon_price(
    *,
    keyword: str = "",
    url: str = "",
    timeout: float = _DEFAULT_FETCH_TIMEOUT,
) -> dict[str, Any]:
    """获取 CEA/CCER/试点等碳价行情摘要。"""
    return await _fetch_sources("price", keyword=keyword, url=url, timeout=timeout)


async def fetch_carbon_policy(
    *,
    keyword: str = "",
    url: str = "",
    timeout: float = _DEFAULT_FETCH_TIMEOUT,
) -> dict[str, Any]:
    """获取双碳政策与公开资讯：官网相关内容 + 站外新闻媒体。

    - 官网优先：仅保留与碳市场/履约主题相关的摘要，无关首页不收录
    - 同步拉取行业新闻站，避免资讯仅来自指定官网
    """
    if url.startswith(("http://", "https://")):
        return await _fetch_sources("policy", keyword=keyword, url=url, timeout=timeout)

    official, news = await asyncio.gather(
        _fetch_sources("policy", keyword=keyword, timeout=timeout),
        _fetch_sources("policy_news", keyword=keyword, timeout=timeout),
        return_exceptions=True,
    )
    if isinstance(official, BaseException):
        official = {
            "ok": False,
            "sources": [],
            "failed_urls": [],
            "summary_md": f"官网政策检索失败（{type(official).__name__}）",
            "error": "official_exception",
        }
    if isinstance(news, BaseException):
        news = {
            "ok": False,
            "sources": [],
            "failed_urls": [],
            "summary_md": f"新闻资讯检索失败（{type(news).__name__}）",
            "error": "news_exception",
        }

    sources = list(official.get("sources") or []) + list(news.get("sources") or [])
    failed = list(official.get("failed_urls") or []) + list(news.get("failed_urls") or [])
    parts: list[str] = []
    if official.get("ok") and official.get("summary_md"):
        parts.append("### 官网政策要点\n\n" + str(official["summary_md"]))
    if news.get("ok") and news.get("summary_md"):
        parts.append("### 公开新闻与行业资讯\n\n" + str(news["summary_md"]))
    if not parts:
        tried = "官网政策站 + 行业新闻站"
        return {
            "ok": False,
            "query_type": "policy",
            "keyword": keyword,
            "queried_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "sources": [],
            "failed_urls": failed,
            "summary_md": (
                f"未获取到与「{keyword or '全国碳市场履约'}」相关的政策/资讯。"
                f"已跳过无关页面；尝试来源：{tried}。"
            ),
            "error": "no_relevant_sources",
        }

    return {
        "ok": True,
        "query_type": "policy",
        "keyword": keyword,
        "queried_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sources": sources,
        "failed_urls": failed,
        "summary_md": "\n\n---\n\n".join(parts),
        "error": None,
    }


async def fetch_carbon_data(
    topic: str,
    *,
    keyword: str = "",
    url: str = "",
    timeout: float = _DEFAULT_FETCH_TIMEOUT,
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
    return await _fetch_sources(t, keyword=keyword, url=url, timeout=timeout)


def news_browser_task_hint(question: str = "") -> str:
    """新闻/资讯类问题的浏览器执行任务提示。"""
    q = (question or "").strip() or "最新双碳新闻资讯"
    urls = "、".join(NEWS_BROWSER_HINT_URLS)
    return (
        f"用浏览器打开碳资讯站点（{urls}）查询并摘要：{q}。"
        "优先打开列表页最新条目，必要时进入详情页核对发布时间与来源。"
    )
