"""Video URL fetcher helpers."""

from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import AppError
from app.integrations.video_url_fetcher import (
    _fetch_with_ytdlp,
    _is_wechat_channel_url,
    fetch_media_from_url,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://weixin.qq.com/sph/AZLGE1pILH", True),
        ("https://channels.weixin.qq.com/finder-preview/pages/sph?id=abc", True),
        ("https://mp.weixin.qq.com/s?__biz=abc", False),
        ("https://example.com/video.mp4", False),
    ],
)
def test_is_wechat_channel_url(url: str, expected: bool) -> None:
    assert _is_wechat_channel_url(url) is expected


def test_fetch_wechat_channel_rejected_before_ytdlp() -> None:
    with pytest.raises(AppError) as exc:
        asyncio.run(
            fetch_media_from_url(
                "https://weixin.qq.com/sph/AZLGE1pILH",
                max_bytes=10 * 1024 * 1024,
            )
        )
    assert "微信视频号" in str(exc.value)


def test_fetch_reports_missing_ytdlp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.integrations.video_url_fetcher._ytdlp_missing_component",
        lambda: "yt-dlp",
    )
    with pytest.raises(AppError) as exc:
        _fetch_with_ytdlp("https://www.bilibili.com/video/BV1xx", max_bytes=10 * 1024 * 1024)
    assert "yt-dlp" in str(exc.value)
