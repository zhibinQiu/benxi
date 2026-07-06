"""本地 speech-service 客户端（Docker Compose）。"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.core.exceptions import bad_request
from app.integrations.whisper_client import validate_audio_filename
from app.services.model_settings_service import get_speech_service_url


def speech_service_url() -> str:
    return get_speech_service_url().rstrip("/")


def local_configured() -> bool:
    return bool(speech_service_url())


async def check_health() -> bool:
    if not local_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{speech_service_url()}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def fetch_remote_meta() -> dict | None:
    if not local_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{speech_service_url()}/meta")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        return None


async def transcribe_audio(
    *,
    content: bytes,
    filename: str,
    language: str | None = None,
    diarize: bool = True,
) -> dict:
    settings = get_settings()
    max_bytes = settings.stt_max_file_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise bad_request(f"音频文件过大，最大 {settings.stt_max_file_mb} MB")
    if not content:
        raise bad_request("音频文件为空")

    safe_name = validate_audio_filename(filename)
    url = f"{speech_service_url()}/transcribe"
    data: dict[str, str] = {"diarize": "true" if diarize else "false"}
    lang = (language or settings.stt_language or "").strip()
    if lang:
        data["language"] = lang
    files = {"file": (safe_name, content)}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            r = await client.post(url, data=data, files=files)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"本地语音转写失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接本地语音服务 ({speech_service_url()}): {e}") from e

    text = (body.get("text") or "").strip()
    if not text:
        raise bad_request("转写结果为空，请检查音频是否包含可识别语音")

    segments = body.get("segments") or []
    return {
        "text": text,
        "language": body.get("language"),
        "duration_seconds": body.get("duration_seconds"),
        "model": body.get("model"),
        "segments": segments,
    }

