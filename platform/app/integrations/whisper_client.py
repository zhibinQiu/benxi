"""OpenAI 兼容 Whisper 语音转写客户端。"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.core.exceptions import bad_request

ACCEPTED_EXTENSIONS = frozenset(
    {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".oga", ".ogg", ".wav", ".webm"}
)


def stt_configured() -> bool:
    return bool(get_settings().stt_api_key.strip())


def validate_audio_filename(filename: str) -> str:
    name = (filename or "").strip()
    if not name:
        raise bad_request("请提供音频文件名")
    ext = ""
    if "." in name:
        ext = name[name.rfind(".") :].lower()
    if ext not in ACCEPTED_EXTENSIONS:
        allowed = ", ".join(sorted(ACCEPTED_EXTENSIONS))
        raise bad_request(f"不支持的音频格式，请使用：{allowed}")
    return name


async def transcribe_audio(
    *,
    content: bytes,
    filename: str,
    language: str | None = None,
) -> dict:
    settings = get_settings()
    api_key = settings.stt_api_key.strip()
    if not api_key:
        raise bad_request("未配置语音转写服务，请在平台环境变量中设置 STT_API_KEY")

    max_bytes = settings.stt_max_file_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise bad_request(f"音频文件过大，最大 {settings.stt_max_file_mb} MB")

    if not content:
        raise bad_request("音频文件为空")

    safe_name = validate_audio_filename(filename)
    url = f"{settings.stt_base_url.rstrip('/')}/audio/transcriptions"
    data: dict[str, str] = {"model": settings.stt_model}
    lang = (language or settings.stt_language or "").strip()
    if lang:
        data["language"] = lang

    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (safe_name, content)}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            r = await client.post(url, headers=headers, data=data, files=files)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"语音转写失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接语音转写服务: {e}") from e

    text = (body.get("text") or "").strip()
    if not text:
        raise bad_request("转写结果为空，请检查音频是否包含可识别语音")

    return {
        "text": text,
        "language": body.get("language"),
        "duration_seconds": body.get("duration"),
        "model": settings.stt_model,
    }
