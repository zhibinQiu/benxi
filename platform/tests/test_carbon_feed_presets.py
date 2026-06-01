"""内置双碳 RSS 预设。"""

from app.integrations.feed_fetcher import CARBON_FEED_PRESETS


def test_carbon_presets_include_user_feeds():
    urls = {p["feed_url"].rstrip("/") for p in CARBON_FEED_PRESETS}
    assert "https://www.carbonbrief.org/rss" in urls
    assert "https://carbon-pulse.com/feed" in urls or "https://carbon-pulse.com/feed/" in urls
    assert "https://ecopowerhub.com/rss" in urls
    assert "https://www.gov.cn/rss/xxgk.xml" in urls


def test_carbon_presets_are_direct_rss():
    for p in CARBON_FEED_PRESETS:
        assert p.get("kind") == "rss"
        assert p.get("feed_url", "").startswith("https://")
