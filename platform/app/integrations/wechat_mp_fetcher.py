"""微信公众号公开页解析（单篇链接 + 可选历史列表）。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_BIZ_RE = re.compile(
    r"(?:__biz|biz)=([A-Za-z0-9_=%]+)",
    re.IGNORECASE,
)
_BIZ_JSON_RE = re.compile(
    r'["\']__biz["\']\s*:\s*["\']([A-Za-z0-9_=%]+)["\']',
    re.IGNORECASE,
)
_BIZ_KV_RE = re.compile(
    r'\bbiz\s*:\s*["\']([A-Za-z0-9_=%]+)["\']',
    re.IGNORECASE,
)


class WechatMpFetchError(RuntimeError):
    pass


@dataclass
class ParsedArticle:
    title: str
    summary: str
    cover_url: str
    author: str
    publish_at: datetime | None
    content_html: str
    original_url: str
    biz: str
    account_name: str
    content_hash: str


def _client_headers(*, referer: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer or "https://mp.weixin.qq.com/",
    }
    return h


def _decode_biz(raw: str) -> str:
    value = (raw or "").strip().strip('"').strip("'")
    if not value:
        return ""
    for _ in range(3):
        try:
            decoded = unquote(value)
        except Exception:
            break
        if decoded == value:
            break
        value = decoded
    return value.strip()


def _looks_like_biz(value: str) -> bool:
    v = (value or "").strip()
    if len(v) < 8:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_=-]+", v):
        return False
    return v.startswith(("Mz", "M", "NA"))


def extract_biz_from_text(text: str) -> str:
    """从 URL / HTML / JS 片段中提取 __biz。"""
    if not text:
        return ""
    for pattern in (_BIZ_JSON_RE, _BIZ_KV_RE, _BIZ_RE):
        for m in pattern.finditer(text):
            candidate = _decode_biz(m.group(1))
            if _looks_like_biz(candidate):
                return candidate
    return ""


def extract_biz_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if "mp.weixin.qq.com" not in parsed.netloc and "weixin.qq.com" not in parsed.netloc:
        return ""
    qs = parse_qs(parsed.query, keep_blank_values=True)
    for key in ("__biz", "biz"):
        raw = (qs.get(key) or [""])[0]
        candidate = _decode_biz(raw)
        if _looks_like_biz(candidate):
            return candidate
    if parsed.fragment:
        frag_qs = parse_qs(parsed.fragment.lstrip("?"), keep_blank_values=True)
        for key in ("__biz", "biz"):
            raw = (frag_qs.get(key) or [""])[0]
            candidate = _decode_biz(raw)
            if _looks_like_biz(candidate):
                return candidate
    return extract_biz_from_text(url)


def _content_hash(url: str, title: str) -> str:
    base = f"{url.strip()}|{title.strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _clamp_db_str(value: str, max_len: int) -> str:
    """入库前截断，避免 VARCHAR 超长导致同步失败（微信链接 query 很长）。"""
    text = (value or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}
        self._in_js_content = False
        self._js_chunks: list[str] = []
        self._capture_tag: str | None = None
        self._capture_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            prop = attr.get("property") or attr.get("name")
            content = attr.get("content")
            if prop and content:
                self.og[prop.lower()] = content
        if tag == "div" and attr.get("id") == "js_content":
            self._in_js_content = True
        if tag in ("h1", "h2") and "rich_media_title" in (attr.get("class") or ""):
            self._capture_tag = tag
            self._capture_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._in_js_content:
            self._in_js_content = False
        if tag == self._capture_tag:
            self._capture_tag = None

    def handle_data(self, data: str) -> None:
        if self._in_js_content:
            self._js_chunks.append(data)
        if self._capture_tag:
            self._capture_chunks.append(data)


def _parse_timestamp_from_html(html: str) -> datetime | None:
    for pattern in (
        r"var\s+ct\s*=\s*['\"]?(\d{10})",
        r"createTime\s*=\s*['\"]?(\d{10})",
        r"publish_time\s*=\s*['\"]?(\d{10})",
        r'"sendtime"\s*:\s*(\d{10})',
    ):
        m = re.search(pattern, html)
        if m:
            try:
                return datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
            except (ValueError, OSError):
                continue
    return None


def _parse_account_name(html: str) -> str:
    for pattern in (
        r'id="js_name"[^>]*>([^<]+)<',
        r'nickname\s*=\s*htmlDecode\("([^"]+)"\)',
        r'"nick_name"\s*:\s*"([^"]+)"',
        r'og:article:author"\s+content="([^"]+)"',
    ):
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            name = unescape(m.group(1).strip())
            if name:
                return name
    return ""


def _normalize_article_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise WechatMpFetchError("文章链接为空")
    if not u.startswith("http"):
        u = f"https://{u}"
    parsed = urlparse(u)
    host = parsed.netloc.lower()
    if "mp.weixin.qq.com" not in host and "weixin.qq.com" not in host:
        raise WechatMpFetchError(
            "仅支持微信公众号文章链接（mp.weixin.qq.com），"
            "请在微信中打开文章后复制链接"
        )
    return u


def _is_blocked_page(html: str, final_url: str) -> bool:
    lower = (html or "").lower()
    url_lower = (final_url or "").lower()
    markers = (
        "环境异常",
        "完成验证后即可继续访问",
        "secitptinput",
        "captcha",
        "/wappoc/waparticlesecurity",
    )
    if any(m in lower for m in markers):
        return True
    return "verify" in url_lower and "mp.weixin.qq.com/s" not in url_lower


def _extract_article_urls_from_html(html: str, *, base: str = "https://mp.weixin.qq.com") -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    patterns = (
        r'https?://mp\.weixin\.qq\.com/s\?[^\s"\'<>]+',
        r'href="(/s\?[^"]+)"',
        r"href='(/s\?[^']+)'",
        r'content_url["\']?\s*:\s*["\'](https?://[^"\']+)',
    )
    for pattern in patterns:
        for m in re.finditer(pattern, html, re.IGNORECASE):
            raw = m.group(1)
            if raw.startswith("http"):
                full = raw.replace("\\/", "/")
            else:
                full = urljoin(base, raw)
            full = unescape(full.split("#")[0].strip())
            if "mp.weixin.qq.com/s" not in full:
                continue
            if full in seen:
                continue
            seen.add(full)
            urls.append(full)
    return urls


def fetch_article(url: str, *, timeout: float = 25.0) -> ParsedArticle:
    """抓取单篇已群发图文（公开页）。"""
    original_url = _normalize_article_url(url)
    biz = extract_biz_from_url(original_url)

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=_client_headers(),
        ) as client:
            r = client.get(original_url)
    except Exception as e:
        raise WechatMpFetchError(f"请求失败: {e}") from e

    if r.status_code >= 400:
        raise WechatMpFetchError(f"HTTP {r.status_code}")

    html = r.text or ""
    final_url = str(r.url)
    if _is_blocked_page(html, final_url):
        raise WechatMpFetchError(
            "微信返回验证/拦截页，请在微信内打开文章后复制完整链接，"
            "或稍后重试"
        )

    if not biz:
        biz = extract_biz_from_url(final_url)
    if not biz:
        biz = extract_biz_from_text(html)

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    title = (
        parser.og.get("og:title")
        or "".join(parser._capture_chunks).strip()
        or "未命名文章"
    )
    cover = parser.og.get("og:image", "")
    summary = parser.og.get("og:description", "")
    content_html = "".join(parser._js_chunks).strip()
    if not content_html and summary:
        content_html = f"<p>{summary}</p>"

    account_name = _parse_account_name(html)
    publish_at = _parse_timestamp_from_html(html)

    if not biz:
        raise WechatMpFetchError(
            "无法解析公众号标识（__biz）。请确认："
            "1) 链接来自微信「复制链接」；"
            "2) 非短链跳转页；"
            "3) 或在添加时手动填写 Biz（链接中 __biz= 后的字符串）"
        )

    return ParsedArticle(
        title=title[:500],
        summary=summary[:2000],
        cover_url=cover[:1000],
        author=account_name[:250],
        publish_at=publish_at,
        content_html=content_html,
        original_url=_clamp_db_str(final_url, 1024),
        biz=biz,
        account_name=account_name,
        content_hash=_content_hash(final_url, title),
    )


def _parse_getmsg_payload(text: str) -> list[dict[str, Any]]:
    payload: dict[str, Any] | None = None
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    if payload is None:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                payload = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []

    if not payload:
        return []

    ret = payload.get("ret")
    if ret not in (0, "0", None):
        logger.debug("wechat getmsg ret=%s msg=%s", ret, payload.get("errmsg"))
        return []

    general_msg = payload.get("general_msg_list") or ""
    if isinstance(general_msg, str):
        try:
            general_msg = json.loads(general_msg)
        except json.JSONDecodeError:
            return []
    if not isinstance(general_msg, dict):
        return []

    items: list[dict[str, Any]] = []
    for block in general_msg.get("list") or []:
        ext = block.get("app_msg_extinfo") or {}
        if isinstance(ext, dict):
            for msg in ext.get("appmsg_info") or []:
                link = msg.get("content_url") or msg.get("link") or ""
                if link.startswith("http"):
                    items.append(
                        {
                            "url": link.replace("\\/", "/"),
                            "title": msg.get("title") or "",
                        }
                    )
        app_msg = block.get("app_msg_list") or []
        if isinstance(app_msg, list):
            for msg in app_msg:
                if not isinstance(msg, dict):
                    continue
                link = msg.get("link") or msg.get("content_url") or ""
                if link.startswith("http"):
                    items.append(
                        {
                            "url": link.replace("\\/", "/"),
                            "title": msg.get("title") or "",
                        }
                    )
    return items


def _fetch_getmsg(biz: str, *, count: int, timeout: float) -> list[dict[str, Any]]:
    encoded = quote(biz, safe="")
    api_url = (
        "https://mp.weixin.qq.com/mp/profile_ext"
        f"?action=getmsg&__biz={encoded}&f=json&offset=0"
        f"&count={min(count, 10)}"
    )
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=_client_headers(referer="https://mp.weixin.qq.com/"),
        ) as client:
            r = client.get(api_url)
    except Exception as e:
        logger.info("wechat getmsg request failed: %s", e)
        return []
    if r.status_code >= 400:
        return []
    return _parse_getmsg_payload(r.text or "")


def _fetch_profile_article_urls(biz: str, *, timeout: float) -> list[str]:
    """从公众号主页 HTML 提取文章链接（getmsg 不可用时的兜底）。"""
    encoded = quote(biz, safe="")
    for path in (
        f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={encoded}&scene=126",
        f"https://mp.weixin.qq.com/mp/homepage?__biz={encoded}&hid=1",
    ):
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers=_client_headers(),
            ) as client:
                r = client.get(path)
        except Exception as e:
            logger.debug("profile fetch %s: %s", path, e)
            continue
        if r.status_code >= 400:
            continue
        urls = _extract_article_urls_from_html(r.text or "", base=str(r.url))
        if urls:
            return urls
    return []


def fetch_recent_articles(
    biz: str, *, count: int = 10, timeout: float = 25.0
) -> tuple[list[dict[str, Any]], str]:
    """拉取最近图文；返回 (条目列表, 说明信息)。"""
    decoded = _decode_biz(biz)
    if not decoded or not _looks_like_biz(decoded):
        return [], "公众号 Biz 无效，请重新添加并填写正确链接"

    items = _fetch_getmsg(decoded, count=count, timeout=timeout)
    if items:
        return items[:count], f"已通过接口拉取 {len(items[:count])} 篇"

    profile_urls = _fetch_profile_article_urls(decoded, timeout=timeout)
    if profile_urls:
        out = [{"url": u, "title": ""} for u in profile_urls[:count]]
        return out, f"已从主页解析 {len(out)} 条链接（将逐篇抓取）"

    return [], (
        "未能拉取历史列表（微信接口限制）。请使用「粘贴链接收录」逐篇添加，"
        "或在微信中重新复制带 __biz= 的完整文章链接后重新添加跟踪"
    )


def resolve_biz_from_url(url: str, *, timeout: float = 25.0) -> str:
    """仅解析 biz，用于校验手动输入。"""
    from_url = extract_biz_from_url(url)
    if _looks_like_biz(from_url):
        return from_url
    try:
        parsed = fetch_article(url, timeout=timeout)
        return parsed.biz
    except WechatMpFetchError:
        raise
    except Exception as e:
        raise WechatMpFetchError(str(e)) from e
