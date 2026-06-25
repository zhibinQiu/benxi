"""通用网页文章解析（手动粘贴链接收录）。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ParsedFeedEntry:
    title: str
    summary: str
    link: str
    content_html: str
    publish_at: datetime | None
    entry_key: str


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_BROWSER_UAS = (
    _DEFAULT_UA,
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
)

_MIN_GOOD_PLAIN_CHARS = 120
_MIN_ACCEPTABLE_PLAIN_CHARS = 40

_CHARSET_META_RE = re.compile(
    rb"""charset\s*=\s*['"]?([a-zA-Z0-9_-]+)""",
    re.I,
)


class WebArticleFetchError(RuntimeError):
    pass


@dataclass
class _FetchAttempt:
    entry: ParsedFeedEntry
    plain_chars: int
    url: str


SITE_WECHAT = "wechat"
SITE_ZHIHU = "zhihu"
SITE_CSDN = "csdn"
SITE_GOV = "gov"
SITE_GENERIC = "generic"


def is_wechat_article_url(url: str) -> bool:
    host = urlparse((url or "").strip()).netloc.lower()
    return "mp.weixin.qq.com" in host or "weixin.qq.com" in host


def is_gov_site_url(url: str) -> bool:
    host = urlparse((url or "").strip()).netloc.lower()
    return host.endswith(".gov.cn") or ".gov.cn" in host or host.endswith(".gov")


def detect_site_kind(url: str) -> str:
    """识别常见收录站点，用于专用解析与请求头。"""
    host = urlparse((url or "").strip()).netloc.lower()
    if is_wechat_article_url(url):
        return SITE_WECHAT
    if "zhihu.com" in host:
        return SITE_ZHIHU
    if "csdn.net" in host:
        return SITE_CSDN
    if is_gov_site_url(url):
        return SITE_GOV
    return SITE_GENERIC


def _entry_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:64]


def _plain_to_html(text: str) -> str:
    from app.integrations.html_markdown import _plain_text_to_html

    return _plain_text_to_html(text) or "<p>暂无正文</p>"


def _plain_text_len(html: str) -> int:
    if not html:
        return 0
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.sub(r"\s+", "", unescape(text)))


def _normalize_input_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise WebArticleFetchError("请填写文章链接")
    if not text.startswith(("http://", "https://")):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
            raise WebArticleFetchError("暂不支持该协议链接")
        text = f"https://{text.lstrip('/')}"
    parsed = urlparse(text)
    if not parsed.netloc:
        raise WebArticleFetchError("请输入有效的 http:// 或 https:// 链接")
    cleaned = urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )
    return cleaned.split("#")[0]


def _candidate_urls(url: str) -> list[str]:
    """同一链接的多种访问方式（https/http、www 变体）。"""
    base = _normalize_input_url(url)
    parsed = urlparse(base)
    out: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        c = (candidate or "").strip().split("#")[0].rstrip("/") or candidate
        if not c or c in seen:
            return
        seen.add(c)
        out.append(c)

    add(base)
    if parsed.scheme == "https":
        add(base.replace("https://", "http://", 1))
    elif parsed.scheme == "http":
        add(base.replace("http://", "https://", 1))

    host = parsed.netloc.lower()
    if host.startswith("www."):
        add(base.replace("://www.", "://", 1))
    elif host:
        add(base.replace("://", "://www.", 1))

    kind = detect_site_kind(base)
    if kind == SITE_ZHIHU and host == "zhuanlan.zhihu.com":
        path = parsed.path or ""
        if path.startswith("/p/"):
            add(f"https://www.zhihu.com{path}")
    if kind == SITE_CSDN and "blog.csdn.net" in host:
        add(base.replace("blog.csdn.net", "www.csdn.net", 1))
    return out


def _site_referers(page_url: str, site_kind: str) -> list[str]:
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    referers = [origin + "/"]
    if site_kind == SITE_ZHIHU:
        referers.extend(
            [
                "https://www.zhihu.com/",
                "https://zhuanlan.zhihu.com/",
            ]
        )
    elif site_kind == SITE_CSDN:
        referers.extend(
            [
                "https://www.csdn.net/",
                "https://blog.csdn.net/",
            ]
        )
    elif site_kind == SITE_GOV:
        referers.append("https://www.gov.cn/")
    seen: set[str] = set()
    out: list[str] = []
    for ref in referers:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def _request_header_sets(page_url: str) -> list[dict[str, str]]:
    site_kind = detect_site_kind(page_url)
    sets: list[dict[str, str]] = []
    for ua in _BROWSER_UAS:
        for referer in _site_referers(page_url, site_kind):
            sets.append(
                {
                    "User-Agent": ua,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Referer": referer,
                    "Upgrade-Insecure-Requests": "1",
                }
            )
    return sets


def _detect_charset(raw: bytes) -> str | None:
    head = raw[:8192]
    m = _CHARSET_META_RE.search(head)
    if m:
        try:
            return m.group(1).decode("ascii", errors="ignore").strip() or None
        except Exception:
            return None
    return None


def _decode_response_text(response: httpx.Response) -> str:
    raw = response.content or b""
    if not raw:
        return ""
    charset = _detect_charset(raw)
    if charset:
        response.encoding = charset
    else:
        response.encoding = response.charset_encoding or response.apparent_encoding or "utf-8"
    try:
        return response.text or ""
    except Exception:
        for enc in ("utf-8", "gb18030", "gbk", "latin-1"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
    return raw.decode("utf-8", errors="replace")


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}
        self.meta: dict[str, str] = {}
        self.itemprop: dict[str, str] = {}
        self._in_article = False
        self._article_chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._ld_json_chunks: list[str] = []
        self._capture_ld_json = False
        self._itemprop_key = ""
        self._itemprop_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            prop = (attr.get("property") or attr.get("name") or "").lower()
            content = attr.get("content")
            if prop and content:
                self.og[prop] = content
                self.meta[prop] = content
            item_key = attr.get("itemprop", "").lower()
            if item_key and content:
                self.itemprop[item_key] = content
        if tag == "script":
            typ = attr.get("type", "").lower()
            if typ == "application/ld+json":
                self._capture_ld_json = True
                self._ld_json_chunks = []
        item_key = attr.get("itemprop", "").lower()
        if item_key and tag != "meta":
            self._itemprop_key = item_key
            self._itemprop_buf = []
        cls = attr.get("class") or ""
        ident = attr.get("id") or ""
        if (
            tag == "article"
            or "article" in cls
            or ident in ("js_content", "article", "content", "main-content")
            or any(
                k in cls
                for k in (
                    "article-content",
                    "post-content",
                    "entry-content",
                    "rich_media_content",
                    "td-post-content",
                    "content-body",
                )
            )
        ):
            self._in_article = True
        if tag == "title":
            self._in_title = True
            self._title_chunks = []
        if tag == "h1":
            self._in_h1 = True
            self._title_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "article":
            self._in_article = False
        if tag == "script" and self._capture_ld_json:
            self._capture_ld_json = False
        if tag in ("title", "h1"):
            self._in_title = False
            self._in_h1 = False
        if self._itemprop_key and tag in ("span", "div", "p", "h1", "section"):
            text = "".join(self._itemprop_buf).strip()
            if text:
                self.itemprop[self._itemprop_key] = text
            self._itemprop_key = ""
            self._itemprop_buf = []

    def handle_data(self, data: str) -> None:
        if self._capture_ld_json:
            self._ld_json_chunks.append(data)
        if self._in_article:
            self._article_chunks.append(data)
        if self._in_title or self._in_h1:
            self._title_chunks.append(data)
        if self._itemprop_key:
            self._itemprop_buf.append(data)


def _iter_json_ld_nodes(data: object):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_json_ld_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_nodes(item)


def _extract_json_ld_fields(html: str) -> tuple[str, str, str]:
    title = ""
    body = ""
    summary = ""
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html,
        re.I,
    ):
        raw = unescape(m.group(1).strip())
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _iter_json_ld_nodes(payload):
            typ = node.get("@type") or node.get("type") or ""
            if isinstance(typ, list):
                types = {str(t).lower() for t in typ}
            else:
                types = {str(typ).lower()}
            if not types & {"article", "newsarticle", "blogposting", "webpage"}:
                continue
            title = title or str(node.get("headline") or node.get("name") or "").strip()
            summary = summary or str(
                node.get("description") or node.get("abstract") or ""
            ).strip()
            article_body = node.get("articleBody") or node.get("text") or ""
            if isinstance(article_body, list):
                article_body = "\n".join(str(x) for x in article_body)
            body = body or str(article_body).strip()
    return title, body, summary


def _best_html_chunk(raw: str, patterns: list[str], *, min_plain: int = 80) -> str:
    best = ""
    best_len = 0
    for pat in patterns:
        for m in re.finditer(pat, raw, re.I):
            chunk = m.group(1)
            plain_len = _plain_text_len(chunk)
            if plain_len > best_len:
                best = chunk
                best_len = plain_len
    if best_len >= min_plain:
        return best
    return ""


def _walk_zhihu_article_nodes(
    data: object,
    *,
    depth: int = 0,
) -> tuple[str, str, str]:
    """从知乎 js-initialData / data-state 等 JSON 中提取标题与正文。"""
    if depth > 14:
        return "", "", ""
    best_title = ""
    best_body = ""
    best_summary = ""
    best_len = 0

    def consider(node: dict) -> None:
        nonlocal best_title, best_body, best_summary, best_len
        title = str(
            node.get("title")
            or node.get("headline")
            or node.get("name")
            or ""
        ).strip()
        summary = str(
            node.get("excerpt")
            or node.get("description")
            or node.get("abstract")
            or ""
        ).strip()
        body = node.get("content") or node.get("articleBody") or node.get("text") or ""
        if isinstance(body, list):
            body = "\n".join(str(x) for x in body)
        body = str(body).strip()
        plain_len = len(re.sub(r"\s+", "", unescape(re.sub(r"<[^>]+>", " ", body))))
        if plain_len > best_len:
            best_len = plain_len
            if title:
                best_title = title
            if body:
                best_body = body
            if summary:
                best_summary = summary

    if isinstance(data, dict):
        consider(data)
        for value in data.values():
            t, b, s = _walk_zhihu_article_nodes(value, depth=depth + 1)
            plain_len = len(re.sub(r"\s+", "", unescape(re.sub(r"<[^>]+>", " ", b))))
            if plain_len > best_len:
                best_len = plain_len
                best_title, best_body, best_summary = t or best_title, b or best_body, s or best_summary
    elif isinstance(data, list):
        for item in data:
            t, b, s = _walk_zhihu_article_nodes(item, depth=depth + 1)
            plain_len = len(re.sub(r"\s+", "", unescape(re.sub(r"<[^>]+>", " ", b))))
            if plain_len > best_len:
                best_len = plain_len
                best_title, best_body, best_summary = t or best_title, b or best_body, s or best_summary
    return best_title, best_body, best_summary


def _extract_zhihu_embedded(html: str) -> tuple[str, str, str]:
    for pattern in (
        r'<script[^>]+id=["\']js-initialData["\'][^>]*>([\s\S]*?)</script>',
        r"<script[^>]+id=[\"']js-initialData[\"'][^>]*>([\s\S]*?)</script>",
    ):
        m = re.search(pattern, html, re.I)
        if not m:
            continue
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        title, body, summary = _walk_zhihu_article_nodes(data)
        if body or title:
            return title, body, summary

    m = re.search(
        r'<div[^>]+id=["\']data["\'][^>]+data-state=(["\'])([\s\S]*?)\1',
        html,
        re.I,
    )
    if m:
        try:
            data = json.loads(unescape(m.group(2)))
        except json.JSONDecodeError:
            data = None
        if data:
            return _walk_zhihu_article_nodes(data)
    return "", "", ""


def _extract_gov_meta(html: str) -> tuple[str, str]:
    title = ""
    summary = ""
    for pattern in (
        r'<meta[^>]+name=["\']ArticleTitle["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title[^>]*>([^<]+)</title>",
    ):
        m = re.search(pattern, html, re.I)
        if m and m.group(1).strip():
            title = unescape(m.group(1).strip())
            break
    for pattern in (
        r'<meta[^>]+name=["\'](?:description|abstract|summary)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        m = re.search(pattern, html, re.I)
        if m and m.group(1).strip():
            summary = unescape(m.group(1).strip())[:2000]
            break
    return title, summary


def _site_html_patterns(site_kind: str) -> list[str]:
    if site_kind == SITE_ZHIHU:
        return [
            r"(<div[^>]*class=[\"'][^\"']*Post-RichContent[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*RichContent-inner[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*RichText[^\"']*ztext[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*AnswerItem[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        ]
    if site_kind == SITE_CSDN:
        return [
            r"(<div[^>]*id=[\"']content_views[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*id=[\"']article_content[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*markdown_views[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*blog-content-box[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        ]
    if site_kind == SITE_GOV:
        return [
            r"(<div[^>]*class=[\"'][^\"']*TRS_Editor[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*id=[\"']zoom[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*Custom_UnionStyle[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*pages_content[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*xlcontent[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*\bzw\b[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*article[^\"']*[\"'][^>]*id=[\"']content[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*detail-article[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        ]
    if site_kind == SITE_WECHAT:
        return [
            r"(<div[^>]*id=[\"']js_content[\"'][^>]*>[\s\S]*?</div>)",
            r"(<div[^>]*class=[\"'][^\"']*rich_media_content[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        ]
    return []


def _extract_article_html(raw: str, *, site_kind: str | None = None) -> str:
    """从整页 HTML 中提取正文区域（保留标签结构）。"""
    if not raw:
        return ""
    kind = site_kind or SITE_GENERIC
    site_chunk = _best_html_chunk(raw, _site_html_patterns(kind))
    if site_chunk:
        return site_chunk

    patterns = [
        r"(<div[^>]*id=[\"']js_content[\"'][^>]*>[\s\S]*?</div>)",
        r"(<div[^>]*class=[\"'][^\"']*rich_media_content[^\"']*[\"'][^>]*>[\s\S]*?</div>)",
        r"(<article[^>]*>[\s\S]*?</article>)",
        (
            r"(<div[^>]*class=[\"'][^\"']*"
            r"(?:entry-content|post-content|article-content|td-content|post-body|"
            r"article-body|content-body|single-content|news-content|text-content|"
            r"detail-content|main-content|content-main|title-article)[^\"']*"
            r"[\"'][^>]*>[\s\S]*?</div>)"
        ),
        r"(<div[^>]*id=[\"'](?:content|article|main-content|js_content|content_views)[\"'][^>]*>[\s\S]*?</div>)",
        r"(<section[^>]*class=[\"'][^\"']*article[^\"']*[\"'][^>]*>[\s\S]*?</section>)",
        r"(<main[^>]*>[\s\S]*?</main>)",
    ]
    patterns = _site_html_patterns(kind) + patterns
    chunk = _best_html_chunk(raw, patterns)
    if chunk:
        return chunk

    body_m = re.search(r"<body[^>]*>([\s\S]*?)</body>", raw, re.I)
    if body_m:
        body = body_m.group(1)
        body = re.sub(
            r"<(script|style|nav|header|footer|aside|iframe)[^>]*>[\s\S]*?</\1>",
            " ",
            body,
            flags=re.I,
        )
        if _plain_text_len(body) >= 80:
            return body.strip()
    return ""


def _is_blocked_page(html: str, site_kind: str) -> bool:
    lower = (html or "").lower()
    if site_kind == SITE_WECHAT:
        markers = (
            "环境异常",
            "完成验证后即可继续访问",
            "secitptinput",
        )
        return any(m in lower for m in markers)
    if site_kind == SITE_ZHIHU:
        if len(html) < 2500 and any(
            m in lower
            for m in (
                "安全验证",
                "unhuman",
                "40362",
                "请输入验证码",
                "访问受限",
            )
        ):
            return True
    if site_kind == SITE_CSDN:
        if "人机验证" in lower or "captcha" in lower and len(html) < 8000:
            return True
    return False


def _fetch_failure_hint(site_kind: str) -> str:
    if site_kind == SITE_ZHIHU:
        return (
            "知乎可能要求登录或触发反爬验证，请在浏览器中打开链接确认可访问后重试"
        )
    if site_kind == SITE_CSDN:
        return "CSDN 可能触发人机验证或文章已删除，请确认链接在浏览器中可正常打开"
    if site_kind == SITE_GOV:
        return "政府网站正文结构多样，若页面需登录或仅内网可访问则无法解析"
    if site_kind == SITE_WECHAT:
        return "微信文章请使用公众号链接（mp.weixin.qq.com），并在微信中复制完整链接"
    return "无法从页面提取正文，请确认链接可公开访问"


def _pick_title(parser: _MetaParser, json_title: str) -> str:
    for key in (
        "og:title",
        "twitter:title",
        "title",
        "article:title",
    ):
        val = parser.og.get(key) or parser.meta.get(key)
        if val and val.strip():
            return val.strip()
    if parser.itemprop.get("headline"):
        return parser.itemprop["headline"].strip()
    if json_title:
        return json_title.strip()
    from_title = "".join(parser._title_chunks).strip()
    if from_title:
        return from_title
    return "未命名文章"


def _pick_summary(parser: _MetaParser, json_summary: str) -> str:
    for key in (
        "og:description",
        "description",
        "twitter:description",
        "article:description",
    ):
        val = parser.og.get(key) or parser.meta.get(key)
        if val and val.strip():
            return val.strip()[:2000]
    if parser.itemprop.get("description"):
        return parser.itemprop["description"].strip()[:2000]
    return (json_summary or "")[:2000]


def _pick_site_title(
    site_kind: str,
    html: str,
    parser: _MetaParser,
    json_title: str,
    embedded_title: str,
) -> str:
    if embedded_title:
        return embedded_title.strip()
    if site_kind == SITE_GOV:
        gov_title, _ = _extract_gov_meta(html)
        if gov_title:
            return gov_title
    if site_kind == SITE_CSDN:
        m = re.search(
            r'<h1[^>]*class=[\"\'][^\"\']*title-article[^\"\']*[\"\'][^>]*>([\s\S]*?)</h1>',
            html,
            re.I,
        )
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1))
            if text.strip():
                return unescape(text.strip())
    if site_kind == SITE_WECHAT:
        m = re.search(
            r'class=[\"\'][^\"\']*rich_media_title[^\"\']*[\"\'][^>]*>([\s\S]*?)</h1>',
            html,
            re.I,
        )
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1))
            if text.strip():
                return unescape(text.strip())
    return _pick_title(parser, json_title)


def _build_entry(html: str, final_url: str) -> ParsedFeedEntry:
    site_kind = detect_site_kind(final_url)
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    json_title, json_body, json_summary = _extract_json_ld_fields(html)
    embedded_title, embedded_body, embedded_summary = "", "", ""
    if site_kind == SITE_ZHIHU:
        embedded_title, embedded_body, embedded_summary = _extract_zhihu_embedded(html)

    title = _pick_site_title(
        site_kind, html, parser, json_title, embedded_title
    )
    summary = _pick_summary(parser, json_summary) or embedded_summary

    if site_kind == SITE_GOV and not summary:
        _, gov_summary = _extract_gov_meta(html)
        summary = gov_summary

    content_html = _extract_article_html(html, site_kind=site_kind)
    if not content_html and embedded_body:
        if "<" in embedded_body and ">" in embedded_body:
            content_html = embedded_body
        else:
            content_html = _plain_to_html(embedded_body)
    if not content_html and json_body:
        if "<" in json_body and ">" in json_body:
            content_html = json_body
        else:
            content_html = _plain_to_html(json_body)
    if not content_html:
        plain = "".join(parser._article_chunks).strip()
        if parser.itemprop.get("articlebody"):
            plain = parser.itemprop["articlebody"].strip() or plain
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


def _score_attempt(attempt: _FetchAttempt) -> int:
    title = attempt.entry.title or ""
    score = attempt.plain_chars
    if title and title != "未命名文章":
        score += 80
    if attempt.entry.summary:
        score += 30
    if attempt.plain_chars >= _MIN_GOOD_PLAIN_CHARS:
        score += 100
    return score


def _attempt_fetch(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
) -> _FetchAttempt | None:
    try:
        response = client.get(url, headers=headers)
    except Exception as e:
        logger.debug("web article fetch failed url=%s: %s", url, e)
        return None
    if response.status_code >= 400:
        logger.debug(
            "web article HTTP %s url=%s", response.status_code, url
        )
        return None
    html = _decode_response_text(response)
    if not html.strip():
        return None
    final_url = str(response.url).split("#")[0]
    site_kind = detect_site_kind(final_url)
    if _is_blocked_page(html, site_kind):
        logger.debug("web article blocked/interstitial url=%s kind=%s", final_url, site_kind)
        return None
    entry = _build_entry(html, final_url)
    plain_chars = _plain_text_len(entry.content_html or "")
    return _FetchAttempt(entry=entry, plain_chars=plain_chars, url=final_url)


def fetch_web_article(url: str, *, timeout: float = 25.0) -> ParsedFeedEntry:
    """抓取并解析网页文章；自动尝试 https/http、浏览器标识与多种正文提取策略。"""
    site_kind = detect_site_kind(url)
    best: _FetchAttempt | None = None
    best_score = -1

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for candidate in _candidate_urls(url):
            saw_response = False
            for idx, headers in enumerate(_request_header_sets(candidate)):
                attempt = _attempt_fetch(client, candidate, headers)
                if attempt is None:
                    if idx == 0:
                        break
                    continue
                saw_response = True
                score = _score_attempt(attempt)
                if score > best_score:
                    best = attempt
                    best_score = score
                if attempt.plain_chars >= _MIN_GOOD_PLAIN_CHARS:
                    return attempt.entry
                if idx == 0 and attempt.plain_chars >= _MIN_ACCEPTABLE_PLAIN_CHARS:
                    break
            if not saw_response:
                continue

    if best and (
        best.plain_chars >= _MIN_ACCEPTABLE_PLAIN_CHARS
        or (best.entry.title and best.entry.title != "未命名文章")
    ):
        return best.entry

    hint = _fetch_failure_hint(site_kind)
    raise WebArticleFetchError(
        f"网页解析失败：{hint}。"
        "已尝试 http/https 与多种浏览器标识；若仍失败，请检查链接是否需要登录。"
    )
