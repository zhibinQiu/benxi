"""通用网页文章解析。"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.integrations.web_article_fetcher import (
    SITE_CSDN,
    SITE_GOV,
    SITE_ZHIHU,
    WebArticleFetchError,
    _build_entry,
    _candidate_urls,
    _decode_response_text,
    _extract_article_html,
    _extract_json_ld_fields,
    _extract_zhihu_embedded,
    _normalize_input_url,
    detect_site_kind,
    fetch_web_article,
    is_gov_site_url,
    is_wechat_article_url,
)


def test_is_wechat_article_url():
    assert is_wechat_article_url("https://mp.weixin.qq.com/s/abc")
    assert not is_wechat_article_url("https://example.com/a")


def test_detect_site_kind():
    assert detect_site_kind("https://mp.weixin.qq.com/s/x") == "wechat"
    assert detect_site_kind("https://zhuanlan.zhihu.com/p/1") == SITE_ZHIHU
    assert detect_site_kind("https://blog.csdn.net/u/article/details/1") == SITE_CSDN
    assert detect_site_kind("https://www.beijing.gov.cn/zwgk/1.html") == SITE_GOV
    assert detect_site_kind("https://example.com/a") == "generic"


def test_is_gov_site_url():
    assert is_gov_site_url("https://www.mee.gov.cn/xxgk/1.html")
    assert not is_gov_site_url("https://example.com/a")


def test_candidate_urls_include_http_https_variants():
    urls = _candidate_urls("https://news.example.com/path?id=1")
    assert "https://news.example.com/path?id=1" in urls
    assert "http://news.example.com/path?id=1" in urls


def test_normalize_input_url_adds_https():
    assert _normalize_input_url("example.com/foo").startswith("https://")


def test_extract_json_ld_fields():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"NewsArticle","headline":"碳市场周报","description":"摘要","articleBody":"正文段落一。正文段落二。"}
    </script>
    </head></html>
    """
    title, body, summary = _extract_json_ld_fields(html)
    assert title == "碳市场周报"
    assert "正文段落" in body
    assert summary == "摘要"


def test_extract_article_html_from_post_content():
    html = """
    <html><body>
    <div class="sidebar">nav</div>
    <div class="post-content"><p>""" + ("内容" * 50) + """</p></div>
    </body></html>
    """
    chunk = _extract_article_html(html)
    assert "post-content" in chunk
    assert "内容" in chunk


def test_build_entry_uses_og_and_article():
    html = """
    <html><head>
    <meta property="og:title" content="网页标题">
    <meta property="og:description" content="网页摘要">
    </head><body>
    <article><p>""" + ("正文" * 40) + """</p></article>
    </body></html>
    """
    entry = _build_entry(html, "https://example.com/a")
    assert entry.title == "网页标题"
    assert "正文" in entry.content_html
    assert entry.summary == "网页摘要"


def test_decode_response_text_gbk():
    raw = "<html><meta charset=gbk><body>中文正文</body></html>".encode("gbk")
    response = httpx.Response(200, content=raw, request=httpx.Request("GET", "http://x"))
    text = _decode_response_text(response)
    assert "中文正文" in text


def test_attempt_fetch_http_fallback():
    from app.integrations.web_article_fetcher import _attempt_fetch

    html = """
    <html><head><meta property="og:title" content="OK"></head>
    <body><article><p>""" + ("成功" * 40) + """</p></article></body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "https":
            return httpx.Response(403, request=request)
        return httpx.Response(
            200,
            text=html,
            request=request,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        bad = _attempt_fetch(
            client, "https://blocked.example.com/a", {"User-Agent": "test"}
        )
        assert bad is None
        good = _attempt_fetch(
            client, "http://blocked.example.com/a", {"User-Agent": "test"}
        )
        assert good is not None
        assert good.entry.title == "OK"


def test_extract_article_html_csdn_content_views():
    body = "CSDN正文" * 60
    html = f"""
    <html><body>
    <div id="content_views"><p>{body}</p></div>
    </body></html>
    """
    chunk = _extract_article_html(html, site_kind=SITE_CSDN)
    assert "content_views" in chunk
    assert "CSDN正文" in chunk


def test_extract_article_html_gov_trs_editor():
    body = "政府通知" * 60
    html = f"""
    <html><head><meta name="ArticleTitle" content="关于某某的通知"></head>
    <body><div class="TRS_Editor"><p>{body}</p></div></body></html>
    """
    chunk = _extract_article_html(html, site_kind=SITE_GOV)
    assert "TRS_Editor" in chunk or "政府通知" in chunk
    entry = _build_entry(html, "https://www.mee.gov.cn/zwgk/1.html")
    assert entry.title == "关于某某的通知"
    assert "政府通知" in entry.content_html


def test_extract_zhihu_embedded_initial_data():
    content = "<p>" + ("知乎专栏正文" * 30) + "</p>"
    payload = {
        "initialState": {
            "entities": {
                "articles": {
                    "123": {
                        "title": "专栏标题",
                        "content": content,
                        "excerpt": "专栏摘要",
                    }
                }
            }
        }
    }
    import json

    html = (
        '<html><script id="js-initialData" type="text/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></html>"
    )
    title, body, summary = _extract_zhihu_embedded(html)
    assert title == "专栏标题"
    assert "知乎专栏正文" in body
    assert summary == "专栏摘要"
    entry = _build_entry(html, "https://zhuanlan.zhihu.com/p/123")
    assert entry.title == "专栏标题"
    assert "知乎专栏正文" in entry.content_html


def test_candidate_urls_zhihu_www_mirror():
    urls = _candidate_urls("https://zhuanlan.zhihu.com/p/99")
    assert "https://www.zhihu.com/p/99" in urls


def test_fetch_web_article_raises_when_all_attempts_fail():
    with patch(
        "app.integrations.web_article_fetcher._candidate_urls",
        return_value=["https://missing.example.com/x"],
    ), patch(
        "app.integrations.web_article_fetcher._attempt_fetch",
        return_value=None,
    ):
        with pytest.raises(WebArticleFetchError):
            fetch_web_article("https://missing.example.com/x")
