"""网页 HTML 内存分析 — 只产出摘要字段，不持久化原文。"""

from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup

_MAX_SNIPPET = 280
_HEADING_TAGS = ("h1", "h2", "h3")


def _clean(text: str) -> str:
    text = unescape(re.sub(r"\s+", " ", (text or ""))).strip()
    return text


def _meta_content(soup: BeautifulSoup, *, name: str = "", prop: str = "") -> str:
    if name:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _clean(str(tag["content"]))
    if prop:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return _clean(str(tag["content"]))
    return ""


def _headings(soup: BeautifulSoup, limit: int = 6) -> list[str]:
    out: list[str] = []
    for tag in soup.find_all(_HEADING_TAGS):
        text = _clean(tag.get_text(" ", strip=True))
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _body_snippet(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.body or soup
    text = _clean(body.get_text(" ", strip=True))
    if len(text) > _MAX_SNIPPET:
        return text[: _MAX_SNIPPET - 1] + "…"
    return text


def analyze_html(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html or "", "lxml")
    title = _clean(soup.title.get_text()) if soup.title else ""
    description = _meta_content(soup, name="description") or _meta_content(
        soup, prop="og:description"
    )
    headings = _headings(soup)
    links = soup.find_all("a", href=True)
    external = 0
    for a in links:
        href = str(a.get("href") or "")
        if href.startswith("http://") or href.startswith("https://"):
            external += 1
    return {
        "title": title or "（无 title）",
        "description": description or "（无 meta 描述）",
        "headings": headings,
        "link_count": len(links),
        "external_link_count": external,
        "snippet": _body_snippet(soup) or "（未能提取正文摘要）",
    }


def build_conclusion(url: str, data: dict[str, object]) -> str:
    headings = data.get("headings") or []
    heading_text = "、".join(headings[:4]) if headings else "（无明显标题）"
    parts = [
        f"URL：{url}",
        f"标题：{data.get('title')}",
        f"描述：{data.get('description')}",
        f"主要标题：{heading_text}",
        f"链接数：{data.get('link_count')}（其中 http(s) 外链 {data.get('external_link_count')}）",
        f"正文摘要：{data.get('snippet')}",
    ]
    return "；".join(parts)
