"""微信公众号链接解析。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.wechat_mp_fetcher import (
    _clamp_db_str,
    _looks_like_biz,
    extract_biz_from_text,
    extract_biz_from_url,
    fetch_article,
    fetch_recent_articles,
)


def test_extract_biz_from_url_query():
    url = (
        "https://mp.weixin.qq.com/s?"
        "__biz=MzA3MjA0ODYzOQ==&mid=2247483700&idx=1&sn=abc"
    )
    assert extract_biz_from_url(url) == "MzA3MjA0ODYzOQ=="


def test_extract_biz_from_html_script():
    assert extract_biz_from_text('biz:"MzIxOTg5MTY0MQ=="') == "MzIxOTg5MTY0MQ=="
    assert extract_biz_from_text('"__biz":"MzIxOTg5MTY0MQ=="') == "MzIxOTg5MTY0MQ=="


def test_looks_like_biz():
    assert _looks_like_biz("MzA3MjA0ODYzOQ==")
    assert not _looks_like_biz("abc")


def test_fetch_article_parses_html():
    html = """
    <html><head>
    <meta property="og:title" content="测试标题" />
    <meta property="og:description" content="摘要文字" />
    <meta property="og:image" content="https://mmbiz.qpic.cn/cover.jpg" />
    </head><body>
    <h1 class="rich_media_title">页面标题</h1>
    <div id="js_content"><p>正文段落</p></div>
    <script>var ct = "1700000000"; var biz = "MzTest123==";</script>
    <span id="js_name">碳中和观察</span>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_resp.url = "https://mp.weixin.qq.com/s?__biz=MzTest123==&mid=1"

    with patch("app.integrations.wechat_mp_fetcher.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = mock_resp
        parsed = fetch_article("https://mp.weixin.qq.com/s?__biz=MzTest123==&mid=1")

    assert parsed.title in ("测试标题", "页面标题")
    assert "正文段落" in parsed.content_html
    assert parsed.biz == "MzTest123=="
    assert parsed.account_name == "碳中和观察"


def test_clamp_db_str_truncates_long_url():
    long = "https://mp.weixin.qq.com/s?" + "a=" + "x" * 2000
    out = _clamp_db_str(long, 1024)
    assert len(out) == 1024
    assert out.startswith("https://mp.weixin.qq.com/s?")


def test_fetch_recent_returns_hint_on_empty():
    with patch(
        "app.integrations.wechat_mp_fetcher._fetch_getmsg",
        return_value=[],
    ), patch(
        "app.integrations.wechat_mp_fetcher._fetch_profile_article_urls",
        return_value=[],
    ):
        items, hint = fetch_recent_articles("MzA3MjA0ODYzOQ==", count=5)
    assert items == []
    assert "未能拉取" in hint or "粘贴链接" in hint
