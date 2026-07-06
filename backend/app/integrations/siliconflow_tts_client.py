"""硅基流动文本转语音（OpenAI 兼容 /v1/audio/speech）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.core.exceptions import bad_request
from app.services.model_settings_service import get_tts_credentials

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
TTS_MODEL = DEFAULT_TTS_MODEL
TTS_PROVIDER = ""

SYSTEM_VOICES: tuple[dict[str, str], ...] = (
    {"id": "alex", "label": "沉稳男声", "gender": "male"},
    {"id": "benjamin", "label": "低沉男声", "gender": "male"},
    {"id": "charles", "label": "磁性男声", "gender": "male"},
    {"id": "david", "label": "欢快男声", "gender": "male"},
    {"id": "anna", "label": "沉稳女声", "gender": "female"},
    {"id": "bella", "label": "激情女声", "gender": "female"},
    {"id": "claire", "label": "温柔女声", "gender": "female"},
    {"id": "diana", "label": "欢快女声", "gender": "female"},
)

EMOTION_PROMPTS: dict[str, str] = {
    "happy": "你能用高兴的情感说吗？",
    "excited": "你能用兴奋的情感说吗？",
    "sad": "你能用悲伤的情感说吗？",
    "angry": "你能用愤怒的情感说吗？",
    "gentle": "你能用温柔的情感说吗？",
}

SUPPORTED_FORMATS = ("mp3", "wav")
DEFAULT_FORMAT = "mp3"
MAX_INPUT_CHARS = 2000


def voice_param(voice_id: str, *, model: str | None = None) -> str:
    vid = (voice_id or "alex").strip() or "alex"
    m = (model or DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL
    return f"{m}:{vid}"


def build_speech_api_url(base: str) -> str:
    """将资源管理中的 API base 规范为 /v1/audio/speech（避免 404 page not found）。"""
    b = (base or "").strip().rstrip("/")
    if not b:
        return ""
    if b.endswith("/audio/speech"):
        return b
    for suffix in ("/chat/completions", "/completions"):
        if b.endswith(suffix):
            b = b[: -len(suffix)].rstrip("/")
            break
    if b.endswith("/v1"):
        return f"{b}/audio/speech"
    return f"{b}/v1/audio/speech"


def build_input_text(*, text: str, emotion: str | None = None) -> str:
    body = (text or "").strip()
    if not body:
        raise bad_request("请输入要合成的文本")
    if len(body) > MAX_INPUT_CHARS:
        raise bad_request(f"文本长度不能超过 {MAX_INPUT_CHARS} 字")
    prompt = EMOTION_PROMPTS.get((emotion or "").strip())
    if prompt:
        return f"{prompt}<|endofprompt|>{body}"
    return body


def resolve_tts_settings(db: Session | None = None) -> tuple[str, str, str]:
    """(api_base, api_key, model_name) 来自资源管理「语音合成」。"""
    base, key, model = get_tts_credentials(db)
    base_clean = (base or "").strip().rstrip("/")
    key_clean = (key or "").strip()
    model_clean = (model or "").strip() or DEFAULT_TTS_MODEL
    return base_clean, key_clean, model_clean


def is_configured(db: Session | None = None) -> bool:
    base, key, _ = resolve_tts_settings(db)
    return bool(base and key)


async def synthesize_speech(
    *,
    db: Session | None,
    text: str,
    voice_id: str = "alex",
    emotion: str | None = None,
    speed: float = 1.0,
    response_format: str = DEFAULT_FORMAT,
) -> tuple[bytes, str]:
    base, key, model = resolve_tts_settings(db)
    if not base or not key:
        raise bad_request(
            "语音合成未配置，请在资源管理中配置「语音合成」的 API URL、模型名与 Key"
            "（语言模型为 DeepSeek 时需单独配置 TTS 服务）"
        )

    if "deepseek" in base.lower():
        raise bad_request(
            "当前 API 地址不支持语音合成。"
            "请在资源管理 → 语音合成 填写 OpenAI 兼容的 TTS API 地址"
        )

    fmt = (response_format or DEFAULT_FORMAT).strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        raise bad_request(f"不支持的音频格式：{fmt}")

    spd = max(0.25, min(4.0, float(speed or 1.0)))
    payload = {
        "model": model,
        "voice": voice_param(voice_id, model=model),
        "input": build_input_text(text=text, emotion=emotion),
        "response_format": fmt,
        "speed": spd,
    }
    url = build_speech_api_url(base)
    if not url:
        raise bad_request("语音合成 API 地址无效，请检查资源管理配置")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        raise bad_request("语音合成请求超时，请缩短文本后重试")
    except httpx.RequestError as exc:
        logger.warning("TTS request failed: %s", exc)
        raise bad_request("无法连接语音合成服务，请检查资源管理中的 API 地址")

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else resp.reason_phrase
        logger.warning("TTS upstream %s url=%s: %s", resp.status_code, url, detail)
        if resp.status_code == 404:
            raise bad_request(
                "语音合成接口不可用（404），请确认资源管理中 API 地址与模型名正确"
            )
        raise bad_request(f"语音合成失败（{resp.status_code}）：{detail}")

    media_type = "audio/mpeg" if fmt == "mp3" else "audio/wav"
    return resp.content, media_type
