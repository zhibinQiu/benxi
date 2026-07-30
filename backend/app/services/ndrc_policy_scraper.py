"""发改委智能云搜索政策爬虫。

入口：https://so.ndrc.gov.cn/s?qt=碳&siteCode=bm04000007&tab=all&toolsStatus=1
搜索列表走 sogw.ndrc.gov.cn API，详情页解析发布时间 / 来源 / 正文全文。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SEARCH_PAGE = "https://so.ndrc.gov.cn/s"
SITE_CODE = "bm04000007"
DEFAULT_KEYWORD = "碳"
DEFAULT_TAB = "all"
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_MAX_BODY_CHARS = 20000
_TOKEN_RE = re.compile(
    r"initPubProperty\(\s*"
    r"'[^']*'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"'([^']*)'\.replace\(/,/g,\s*\"\"\)\s*,\s*"
    r"'([^']*)'\s*,\s*"
    r"'[^']*'\s*,\s*"
    r"attrs\s*,\s*"
    r"'([^']*)'\s*,\s*"
    r"\d+\s*,\s*"
    r"\"[^\"]*\"\s*==\s*'[^']*'\s*,\s*"
    r"'([^']*)'\s*\)",
    re.S,
)


class NdrcPolicySearcher:
    """发改委智能云搜索：列表 + 详情全文。"""

    def __init__(
        self,
        *,
        keyword: str = DEFAULT_KEYWORD,
        delay: float = 0.35,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.keyword = (keyword or DEFAULT_KEYWORD).strip() or DEFAULT_KEYWORD
        self.delay = max(0.0, float(delay))
        self._owned_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            verify=False,
            follow_redirects=True,
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        self.api_base = "https://sogw.ndrc.gov.cn/apiservice/"
        self.timestamp = ""
        self.word_token = ""
        self.suid = ""
        self.total_hits = 0

    async def aclose(self) -> None:
        if self._owned_client:
            await self.client.aclose()

    async def _sleep(self) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

    async def refresh_token(self) -> None:
        resp = await self.client.get(
            SEARCH_PAGE,
            params={
                "qt": self.keyword,
                "siteCode": SITE_CODE,
                "tab": DEFAULT_TAB,
                "toolsStatus": "1",
            },
        )
        resp.raise_for_status()
        html = resp.text
        match = _TOKEN_RE.search(html)
        if not match:
            raise RuntimeError("未能从发改委搜索页解析 token，页面结构可能已变更")
        self.timestamp = match.group(1).replace(",", "")
        self.word_token = match.group(2)
        self.api_base = match.group(3)
        self.suid = match.group(4)

    async def search_page(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.word_token:
            await self.refresh_token()

        data = {
            "siteCode": SITE_CODE,
            "tab": DEFAULT_TAB,
            "timestamp": self.timestamp,
            "wordToken": self.word_token,
            "page": page,
            "pageSize": page_size,
            "qt": self.keyword,
            "timeOption": 0,
            "sort": "dateDesc",
            "keyPlace": 0,
            "fileType": "",
            "toolsStatus": 1,
        }
        headers = {
            "suid": self.suid,
            "Origin": "https://so.ndrc.gov.cn",
            "Referer": (
                f"{SEARCH_PAGE}?qt={quote(self.keyword)}"
                f"&siteCode={SITE_CODE}&tab={DEFAULT_TAB}&toolsStatus=1"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = await self.client.post(f"{self.api_base}s", data=data, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

        if not payload.get("ok"):
            await self.refresh_token()
            data["timestamp"] = self.timestamp
            data["wordToken"] = self.word_token
            headers["suid"] = self.suid
            resp = await self.client.post(
                f"{self.api_base}s", data=data, headers=headers
            )
            resp.raise_for_status()
            payload = resp.json()

        return payload

    async def iter_list_items(self, max_pages: int, page_size: int = 20):
        for page in range(1, max_pages + 1):
            await self._sleep()
            payload = await self.search_page(page=page, page_size=page_size)
            search = (payload.get("data") or {}).get("search") or {}
            if page == 1:
                self.total_hits = int(search.get("totalHits") or 0)

            docs = search.get("searchs") or []
            if not docs:
                break

            for doc in docs:
                yield {
                    "title": _clean_html(
                        doc.get("title") or doc.get("disPlayTitle") or ""
                    ),
                    "url": doc.get("viewUrl") or "",
                    "doc_type": doc.get("displayDb") or "",
                }

            if page * page_size >= self.total_hits:
                break

    async def fetch_detail(self, url: str) -> dict[str, str]:
        empty = {"published_at": "", "source": "", "body": ""}
        if not url:
            return empty

        await self._sleep()
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPError as exc:
            logger.debug("ndrc detail fetch failed url=%s err=%s", url, exc)
            return empty

        soup = BeautifulSoup(html, "lxml")
        return {
            "published_at": _extract_publish_time(soup),
            "source": _extract_source(soup),
            "body": _extract_full_text(soup),
        }

    async def scrape(
        self,
        *,
        max_pages: int = 1,
        page_size: int = 10,
        with_detail: bool = True,
    ) -> list[dict[str, str]]:
        await self.refresh_token()
        rows: list[dict[str, str]] = []
        async for item in self.iter_list_items(max_pages=max_pages, page_size=page_size):
            if with_detail:
                detail = await self.fetch_detail(item["url"])
                item = {**item, **detail}
            else:
                item = {**item, "published_at": "", "source": "", "body": ""}
            rows.append(item)
        return rows


def _clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return ""


def _extract_publish_time(soup: BeautifulSoup) -> str:
    for name in ("PubDate", "pubdate", "publishdate", "PubTime"):
        value = _meta(soup, name)
        if value:
            return value

    time_node = soup.select_one(".time, .pubtime, .publish-time, .article-info .date")
    if time_node:
        text = time_node.get_text(" ", strip=True)
        text = re.sub(r"^发布时间[:：]?\s*", "", text)
        if text:
            return text

    body_text = soup.get_text("\n", strip=True)
    match = re.search(
        r"发布时间[:：]\s*([0-9]{4}[-/年.][0-9]{1,2}[-/月.][0-9]{1,2}"
        r"(?:\s*[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)?)",
        body_text,
    )
    return match.group(1) if match else ""


def _extract_source(soup: BeautifulSoup) -> str:
    for name in ("ContentSource", "Source", "contentSource"):
        value = _meta(soup, name)
        if value:
            return value

    source_node = soup.select_one(".ly, .laiyuan, .source, .laiyuantxt, .laiyuantext")
    if source_node:
        text = source_node.get_text(" ", strip=True)
        text = re.sub(r"^来源[:：]?\s*", "", text)
        if text:
            return text

    body_text = soup.get_text("\n", strip=True)
    match = re.search(r"来源[:：]\s*([^\n\r]{1,40})", body_text)
    return match.group(1).strip() if match else ""


def _node_text(node) -> str:
    text = node.get_text(" ", strip=True)
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def _is_title_like(node, text: str) -> bool:
    style = (node.get("style") or "").replace(" ", "").lower()
    parent_style = ""
    if node.parent:
        parent_style = (node.parent.get("style") or "").replace(" ", "").lower()
    centered = "text-align:center" in style or "text-align:center" in parent_style
    if centered and len(text) < 80:
        return True
    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z〔〕\[\]0-9\s\-—]{2,40}", text):
        if "号" in text or len(text) <= 20:
            return True
    return False


def _content_containers(soup: BeautifulSoup) -> list:
    for selector in (
        ".TRS_Editor",
        ".article_con",
        ".article-content",
        ".content",
        "#Zoom",
        ".pages_content",
        ".detail-content",
    ):
        found = soup.select(selector)
        if found:
            return list(found)
    return [soup]


def _iter_leaf_blocks(container):
    for node in container.find_all(["p", "div", "span"], recursive=True):
        if node.find(["p", "div", "span"]):
            continue
        if node.find(["table", "img"]) and not _node_text(node):
            continue
        yield node


def _is_noise_paragraph(text: str) -> bool:
    if len(text) < 8:
        return True
    if text.startswith(("分享到", "相关稿件", "附件", "扫一扫", "打印", "关闭")):
        return True
    return False


def _extract_full_text(soup: BeautifulSoup) -> str:
    """提取详情页正文全文（多段拼接），而非仅首段。"""
    paragraphs: list[str] = []
    seen: set[str] = set()

    for container in _content_containers(soup):
        for node in _iter_leaf_blocks(container):
            text = _node_text(node)
            if _is_noise_paragraph(text):
                continue
            if _is_title_like(node, text):
                continue
            if text in seen:
                continue
            seen.add(text)
            paragraphs.append(text)

    if not paragraphs:
        # 回退：整页可见文本粗过滤
        raw = soup.get_text("\n", strip=True)
        for line in raw.split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) < 20:
                continue
            if _is_noise_paragraph(line):
                continue
            if line not in seen:
                seen.add(line)
                paragraphs.append(line)

    body = "\n\n".join(paragraphs).strip()
    if len(body) > _MAX_BODY_CHARS:
        return body[:_MAX_BODY_CHARS] + "…"
    return body
