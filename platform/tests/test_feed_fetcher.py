"""RSS/Atom 解析。"""

from app.integrations.feed_fetcher import fetch_feed, resolve_feed_url


def test_fetch_rss_xml():
    xml = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>测试频道</title>
        <item>
          <title>条目一</title>
          <link>https://example.com/a</link>
          <guid>guid-1</guid>
          <description>摘要</description>
        </item>
      </channel>
    </rss>
    """
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock(status_code=200, content=xml.encode(), url="https://ex.com/rss")
    with patch("app.integrations.feed_fetcher.httpx.Client") as cls:
        cls.return_value.__enter__.return_value.get.return_value = mock_resp
        meta, entries = fetch_feed("https://example.com/rss")
    assert meta.title == "测试频道"
    assert len(entries) == 1
    assert entries[0].title == "条目一"


def test_resolve_direct_feed_url():
    url, site = resolve_feed_url("https://example.com/feed.xml", kind="rss")
    assert url.endswith("feed.xml")
    assert site == url
