"""从公开 HTTP(S) 链接获取音视频字节，供语音转写。"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.exceptions import bad_request
from app.integrations.browser_automation.url_guard import validate_browser_url

MEDIA_EXTENSIONS = frozenset(
    {
        ".avi",
        ".flac",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".mpga",
        ".oga",
        ".ogg",
        ".wav",
        ".webm",
    }
)

_CONTENT_TYPE_MEDIA = re.compile(r"^(audio|video)/", re.I)

_VIDEO_PLATFORM_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "b23.tv",
    "v.qq.com",
    "iqiyi.com",
    "youku.com",
    "douyin.com",
    "iesdouyin.com",
)

_WECHAT_CHANNEL_HOSTS = frozenset({"weixin.qq.com", "channels.weixin.qq.com"})


def _ytdlp_missing_component() -> str | None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return "yt-dlp"
    if not shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def video_url_fetch_available() -> bool:
    """直链下载始终可用；平台页解析依赖 yt-dlp + ffmpeg。"""
    return bool(shutil.which("ffmpeg"))


def ytdlp_available() -> bool:
    return _ytdlp_missing_component() is None


def _yt_dlp_cmd() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _is_video_platform(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _VIDEO_PLATFORM_SUFFIXES)


def _is_wechat_channel_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _WECHAT_CHANNEL_HOSTS and not any(
        host.endswith(f".{suffix}") for suffix in _WECHAT_CHANNEL_HOSTS
    ):
        return False
    path = parsed.path.lower()
    query = parsed.query.lower()
    return "/sph/" in path or "finder" in path or "sph" in query or host.startswith("channels.")


def _looks_like_direct_media(url: str, content_type: str | None = None) -> bool:
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in MEDIA_EXTENSIONS):
        return True
    return bool(content_type and _CONTENT_TYPE_MEDIA.match(content_type))


def _guess_filename(url: str, content_type: str | None = None) -> str:
    name = Path(urlparse(url).path).name
    if name and "." in name:
        return name
    if content_type and "audio" in content_type.lower():
        return "media.mp3"
    return "media.mp4"


async def fetch_media_from_url(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 180.0,
) -> tuple[bytes, str]:
    """下载或提取链接中的音视频，返回 (bytes, filename)。"""
    safe_url = validate_browser_url((url or "").strip())
    if not safe_url:
        raise bad_request("请提供有效的视频或音频链接")

    if _is_wechat_channel_url(safe_url):
        raise bad_request(_wechat_channel_unsupported_message())

    if _is_video_platform(safe_url) or not _looks_like_direct_media(safe_url):
        return _fetch_with_ytdlp(safe_url, max_bytes=max_bytes)

    try:
        return await _fetch_direct(safe_url, max_bytes=max_bytes, timeout=timeout)
    except bad_request:
        raise
    except httpx.HTTPError:
        if ytdlp_available():
            return _fetch_with_ytdlp(safe_url, max_bytes=max_bytes)
        raise bad_request("无法下载该链接，请确认地址可公开访问且为音视频直链")


async def _fetch_direct(url: str, *, max_bytes: int, timeout: float) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type")
            if not _looks_like_direct_media(url, content_type):
                raise bad_request("链接内容不是音视频文件")

            chunks: list[bytes] = []
            total = 0
            for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise bad_request(f"文件过大，最大 {max_bytes // (1024 * 1024)} MB")
                chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise bad_request("下载内容为空")
    return content, _guess_filename(url, content_type)


def _wechat_channel_unsupported_message() -> str:
    return (
        "微信视频号链接暂不支持。"
        "请上传本地音视频文件，或使用 B 站、YouTube 等公开链接及 mp4/mp3 直链。"
    )


def _ytdlp_unavailable_message() -> str:
    missing = _ytdlp_missing_component() or "yt-dlp"
    return (
        f"当前环境未安装 {missing}，仅支持音视频直链。"
        "本机开发请执行 ./dev.sh local restart；"
        "服务器请重建平台镜像（需含 yt-dlp 与 ffmpeg）。"
    )


def _fetch_with_ytdlp(url: str, *, max_bytes: int) -> tuple[bytes, str]:
    if not ytdlp_available():
        raise bad_request(_ytdlp_unavailable_message())

    max_mb = max(1, max_bytes // (1024 * 1024))
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = str(Path(tmpdir) / "audio.%(ext)s")
        cmd = [
            *_yt_dlp_cmd(),
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "5",
            "-o",
            out_template,
            "--no-playlist",
            "--max-filesize",
            f"{max_mb}M",
            "--no-warnings",
            url,
        ]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as e:
            raise bad_request("视频下载超时，请稍后重试或使用较短的视频") from e

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "未知错误").strip()[:500]
            raise bad_request(f"视频解析失败：{detail}")

        files = sorted(Path(tmpdir).glob("audio.*"))
        if not files:
            raise bad_request("未能从链接提取音频，请确认链接可公开访问")

        path = files[0]
        content = path.read_bytes()
        if len(content) > max_bytes:
            raise bad_request(f"文件过大，最大 {max_mb} MB")
        if not content:
            raise bad_request("提取的音频为空")
        return content, path.name
