"""通用网页文章解析（手动粘贴链接收录，非 RSS 批量订阅）。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.integrations.feed_fetcher import ParsedFeedEntry

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class WebArticleFetchError(RuntimeError):
    pass


def is_wechat_article_url(url: str) -> bool:
    host = urlparse((url or "").strip()).netloc.lower()
    return "mp.weixin.qq.com" in host or "weixin.qq.com" in host


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}
        self._in_article = False
        self._article_chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            prop = attr.get("property") or attr.get("name")
            content = attr.get("content")
            if prop and content:
                self.og[prop.lower()] = content
        cls = attr.get("class") or ""
        if tag == "article" or "article" in cls or attr.get("id") == "js_content":
            self._in_article = True
        if tag in ("h1", "title") and not self._in_title:
            self._in_title = True
            self._title_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "article":
            self._in_article = False
        if tag in ("h1", "title"):
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_article:
            self._article_chunks.append(data)
        if self._in_title:
            self._title_chunks.append(data)


def _entry_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:64]


def _plain_to_html(text: str) -> str:
    from app.integrations.html_markdown import _plain_text_to_html

    return _plain_text_to_html(text) or "<p>暂无正文</p>"


def _extract_article_html(raw: str) -> str:
    """从整页 HTML 中提取正文区域（保留标签结构）。"""
    if not raw:
        return ""
    patterns = [
        r"(<div[^>]*id=[\"']js_content[\"'][^>]*>[\s\S]*?</div>)",
        r"(<div[^>]*class=[\"'][^\"']*rich_media_content[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        r"(<article[^>]*>[\s\S]*?</article>)",
        (
            r"(<div[^>]*class=[\"'][^\"']*"
            r"(?:entry-content|post-content|article-content|td-content|post-body)[^\"']*"
            r"[\"'][^>]*>[\s\S]*?</div>)"
        ),
        r"(<main[^>]*>[\s\S]*?</main>)",
    ]
    for pat in patterns:
        m = re.search(pat, raw, re.I)
        if not m:
            continue
        chunk = m.group(1)
        plain_len = len(re.sub(r"<[^>]+>", "", chunk))
        if plain_len >= 80:
            return chunk
    return ""


def fetch_web_article(url: str, *, timeout: float = 25.0) -> ParsedFeedEntry:
    original = (url or "").strip()
    if not original.startswith(("http://", "https://")):
        raise WebArticleFetchError("请输入以 http:// 或 https:// 开头的链接")

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        ) as client:
            r = client.get(original)
    except Exception as e:
        raise WebArticleFetchError(f"请求失败: {e}") from e

    if r.status_code >= 400:
        raise WebArticleFetchError(f"HTTP {r.status_code}")

    html = r.text or ""
    final_url = str(r.url).split("#")[0]

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    title = (
        parser.og.get("og:title")
        or "".join(parser._title_chunks).strip()
        or "未命名文章"
    )
    summary = parser.og.get("og:description", "")[:2000]
    content_html = _extract_article_html(html)
    if not content_html:
        plain = "".join(parser._article_chunks).strip()
        if plain:
            content_html = _plain_to_html(plain)
        elif summary:
            content_html = _plain_to_html(summary)
        else:
            content_html = "<p>暂无正文</p>"

    return ParsedFeedEntry(
        title=title[:500],
        summary=summary,
        link=final_url[:1024],
        content_html=content_html,
        publish_at=datetime.now(timezone.utc),
        entry_key=_entry_key(final_url),
    )
