"""RSS/Atom 抓取与网站 Feed 发现。"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 双碳相关内置订阅源（侧栏一键添加；kind=rss 为直链 Feed，可直接用于 Feedly/Inoreader 同类地址）
CARBON_FEED_PRESETS: list[dict[str, str]] = [
    # 国际 RSS
    {
        "name": "Carbon Brief",
        "feed_url": "https://www.carbonbrief.org/rss",
        "site_url": "https://www.carbonbrief.org",
        "kind": "rss",
        "category": "国际双碳",
    },
    {
        "name": "Carbon Pulse",
        "feed_url": "https://carbon-pulse.com/feed/",
        "site_url": "https://carbon-pulse.com",
        "kind": "rss",
        "category": "国际双碳",
    },
    {
        "name": "EcoPowerHub",
        "feed_url": "https://ecopowerhub.com/rss",
        "site_url": "https://ecopowerhub.com",
        "kind": "rss",
        "category": "国际双碳",
    },
    # 国内政策 RSS（中国政府网）
    {
        "name": "中国政府网·信息公开",
        "feed_url": "https://www.gov.cn/rss/xxgk.xml",
        "site_url": "https://www.gov.cn",
        "kind": "rss",
        "category": "国内政策",
    },
]
# 注：Feedspot 合集页 https://rss.feedspot.com/carbon_rss_feeds/ 为 HTML 目录，非 RSS/Atom 地址，
# 无法在阅读器中直接订阅；请从该页挑选具体源后手动添加。


class FeedFetchError(RuntimeError):
    pass


@dataclass
class ParsedFeedEntry:
    title: str
    summary: str
    link: str
    content_html: str
    publish_at: datetime | None
    entry_key: str


@dataclass
class ParsedFeedMeta:
    title: str
    description: str
    link: str


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        if re.match(r"^\d{10}$", value):
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        if re.match(r"^\d{13}$", value):
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    class _Strip(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    p = _Strip()
    try:
        p.feed(text or "")
    except Exception:
        return text or ""
    return "".join(p.parts).strip()


def _entry_key(link: str, guid: str, title: str) -> str:
    base = (guid or link or title or "").strip()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _normalize_feed_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise FeedFetchError("订阅地址为空")
    if not u.startswith("http"):
        u = f"https://{u}"
    return u


def discover_feed_url(site_url: str, *, timeout: float = 20.0) -> str | None:
    """从网站首页发现 RSS/Atom 链接。"""
    page_url = _normalize_feed_url(site_url)
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _DEFAULT_UA}
        ) as client:
            r = client.get(page_url)
    except Exception as e:
        raise FeedFetchError(f"无法访问网站: {e}") from e
    if r.status_code >= 400:
        raise FeedFetchError(f"网站 HTTP {r.status_code}")
    html = r.text or ""
    patterns = [
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/rss\+xml',
        r'<link[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/atom\+xml',
    ]
    from urllib.parse import urljoin

    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            href = m.group(1).strip()
            return urljoin(str(r.url), href)
    if re.search(r"<rss\b", html, re.I) or re.search(r"<feed\b", html, re.I):
        return str(r.url)
    return None


def _parse_rss_channel(channel: ET.Element) -> ParsedFeedMeta:
    title = ""
    desc = ""
    link = ""
    for child in channel:
        tag = _local(child.tag)
        if tag == "title" and child.text:
            title = child.text.strip()
        elif tag in ("description", "subtitle") and child.text:
            desc = child.text.strip()
        elif tag == "link" and child.text:
            link = child.text.strip()
    return ParsedFeedMeta(title=title, description=desc, link=link)


def _parse_rss_item(item: ET.Element) -> ParsedFeedEntry | None:
    title = link = guid = summary = content = ""
    published: datetime | None = None
    for child in item:
        tag = _local(child.tag)
        text = (child.text or "").strip()
        if tag == "title":
            title = text
        elif tag == "link":
            link = text
        elif tag == "guid":
            guid = text
        elif tag in ("description", "summary"):
            summary = text
        elif tag in ("content:encoded", "encoded") and text:
            content = text
        elif tag == "pubDate":
            published = _parse_datetime(text)
    if not title and not link:
        return None
    html_body = content or summary
    if html_body and "<" not in html_body:
        html_body = f"<p>{html_body}</p>"
    return ParsedFeedEntry(
        title=title[:500] or "未命名条目",
        summary=_strip_html(summary)[:2000],
        link=link,
        content_html=html_body,
        publish_at=published,
        entry_key=_entry_key(link, guid, title),
    )


def _parse_atom_entry(entry: ET.Element) -> ParsedFeedEntry | None:
    title = link = entry_id = summary = content = ""
    published: datetime | None = None
    for child in entry:
        tag = _local(child.tag)
        if tag == "title" and child.text:
            title = child.text.strip()
        elif tag == "id" and child.text:
            entry_id = child.text.strip()
        elif tag == "link":
            rel = child.attrib.get("rel", "alternate")
            href = child.attrib.get("href", "")
            if href and rel in ("alternate", ""):
                link = href
        elif tag in ("summary", "description") and child.text:
            summary = child.text.strip()
        elif tag == "content" and child.text:
            content = child.text.strip()
        elif tag in ("published", "updated") and child.text:
            published = _parse_datetime(child.text.strip())
    if not title and not link:
        return None
    html_body = content or summary
    if html_body and "<" not in html_body:
        html_body = f"<p>{html_body}</p>"
    return ParsedFeedEntry(
        title=title[:500] or "未命名条目",
        summary=_strip_html(summary)[:2000],
        link=link,
        content_html=html_body,
        publish_at=published,
        entry_key=_entry_key(link, entry_id, title),
    )


def fetch_feed(
    feed_url: str, *, limit: int = 30, timeout: float = 25.0
) -> tuple[ParsedFeedMeta, list[ParsedFeedEntry]]:
    url = _normalize_feed_url(feed_url)
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _DEFAULT_UA}
        ) as client:
            r = client.get(url)
    except Exception as e:
        raise FeedFetchError(f"拉取订阅源失败: {e}") from e
    if r.status_code >= 400:
        raise FeedFetchError(f"订阅源 HTTP {r.status_code}")

    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        raise FeedFetchError(f"无法解析 RSS/Atom: {e}") from e

    tag = _local(root.tag).lower()
    meta = ParsedFeedMeta(title="", description="", link=str(r.url))
    entries: list[ParsedFeedEntry] = []

    if tag == "rss":
        channel = root.find("channel")
        if channel is not None:
            meta = _parse_rss_channel(channel)
            for item in channel.findall("item"):
                parsed = _parse_rss_item(item)
                if parsed:
                    entries.append(parsed)
    elif tag == "feed":
        meta = ParsedFeedMeta(
            title=(root.findtext("{*}title") or root.findtext("title") or "").strip(),
            description=(root.findtext("{*}subtitle") or "").strip(),
            link=str(r.url),
        )
        for item in root.findall("{*}entry"):
            parsed = _parse_atom_entry(item)
            if parsed:
                entries.append(parsed)
        if not entries:
            for item in root.findall("entry"):
                parsed = _parse_atom_entry(item)
                if parsed:
                    entries.append(parsed)
    else:
        raise FeedFetchError("不支持的订阅格式，请使用 RSS 2.0 或 Atom")

    return meta, entries[:limit]


def resolve_feed_url(url: str, *, kind: str = "rss") -> tuple[str, str | None]:
    """返回 (feed_url, site_url)。网站模式尝试自动发现 Feed。"""
    raw = _normalize_feed_url(url)
    lower = raw.lower()
    if lower.endswith((".xml", "/rss", "/feed", "/atom")) or "rss" in lower or "feed" in lower:
        return raw, raw
    if kind == "website" or not lower.endswith(".xml"):
        discovered = discover_feed_url(raw)
        if discovered:
            return discovered, raw
    raise FeedFetchError(
        "未找到 RSS/Atom 地址。请填写订阅链接（常见路径 /rss、/feed），"
        "或提供可直接访问的 .xml 订阅地址"
    )
